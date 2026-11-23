"""Build a static, server-less demo of SARAS in demo/dist/.
Real API responses are snapshotted from a freshly seeded in-memory DB and replayed by a tiny mock
API in the browser (window.SARAS_DEMO_API). Writes are accepted and kept in memory only.
Run from the project root:  python demo/build_demo.py"""
import json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.seed import run as seed

ROOT = pathlib.Path(__file__).resolve().parents[1]
WEB, DIST = ROOT / "app" / "web", ROOT / "demo" / "dist"
app = create_app(TestConfig)
with app.app_context():
    db.create_all(); seed(app, verbose=False)

def client(u, p):
    c = app.test_client(); assert c.post("/api/login", json={"username": u, "password": p}).status_code == 200; return c

snap = {"student": {}, "faculty": {}, "admin": {}}
def grab(role, c, url):
    r = c.get(url); assert r.status_code == 200, (url, r.status_code)
    snap[role][url] = r.get_json(); return snap[role][url]

st, tc, ad = client("akash", "akash123"), client("khan", "khan123"), client("admin", "admin123")
sems = grab("student", st, "/api/semesters"); grab("faculty", tc, "/api/semesters"); grab("admin", ad, "/api/semesters")
sem_list = sems if isinstance(sems, list) else sems.get("semesters", sems)
for s in sem_list:
    grab("student", st, f"/api/student/dashboard?semester_id={s['id']}")
    td = grab("faculty", tc, f"/api/teacher/dashboard?semester_id={s['id']}")
    for c in td["courses"]:
        o = c["offering_id"]
        for ep in ("roster", "analytics", "feedback", "grade-rules", "gradebook", "upload-status"):
            grab("faculty", tc, f"/api/teacher/offerings/{o}/{ep}")
grab("student", st, "/api/student/dashboard"); grab("faculty", tc, "/api/teacher/dashboard")
grab("student", st, "/api/student/offerings"); grab("faculty", tc, "/api/teacher/integrity")
for ep in ("overview", "departments", "faculty", "courses", "integrity"):
    grab("admin", ad, f"/api/admin/{ep}")
page, allp = 1, []
while True:
    d = grab("admin", ad, f"/api/admin/students?q=&page={page}")
    allp += d["items"]
    if page * d.get("per_page", len(d["items"]) or 1) >= d.get("total", 0) or not d["items"]: break
    page += 1
snap["admin_students_all"] = allp

MOCK = r"""
(function(){
const SNAP=__SNAP__, ROLE='__ROLE__', S=SNAP[ROLE], T=s=>JSON.parse(JSON.stringify(s));
const wait=ms=>new Promise(r=>setTimeout(r,ms));
const fail=(m,status=400)=>{throw Object.assign(new Error(m),{status,data:{error:m}})};
function find(u){ if(u in S) return T(S[u]); const p=u.split('?')[0];
  if(p==='/api/admin/students'){const q=(new URLSearchParams(u.split('?')[1]||'').get('q')||'').toLowerCase();
    const base=T(S['/api/admin/students?q=&page=1']);const all=SNAP.admin_students_all.filter(s=>!q||s.name.toLowerCase().includes(q)||String(s.roll_no).includes(q));
    base.items=all.slice(0,25);base.total=all.length;return base}
  const k=Object.keys(S).find(k=>k.split('?')[0]===p); if(k) return T(S[k]);
  const sem=Object.keys(S).find(k=>k.startsWith(p+'?semester_id=')); if(sem) return T(S[sem]);
  fail('Not available in the static demo: '+p,404)}
const extra={integ:new Set()};
window.SARAS_DEMO_API={demo:true,
 async get(u){await wait(60);let d=find(u);
   if(/integrity$/.test(u.split('?')[0])&&d.alerts)d.alerts=d.alerts.filter(a=>!extra.integ.has(a.id));return d},
 async post(u,b){await wait(80);b=b||{};
   if(u.endsWith('/logout'))return{ok:true};
   if(/integrity\/resolve-all$/.test(u)){(find('/api/teacher/integrity').alerts||[]).forEach(a=>extra.integ.add(a.id));return{ok:true}}
   const m=u.match(/integrity\/(.+)(?:\/resolve)?$/); if(m&&/integrity/.test(u)){extra.integ.add(decodeURIComponent(m[1].replace(/\/resolve$/,'')));return{ok:true}}
   if(/\/results$/.test(u)){const n=(b.rows||[]).length;return{ok:true,processed:n,total:n,status:'OK',errors:[]}}
   if(/\/enroll$/.test(u)||/\/enrollments$/.test(u))return{ok:true,enrollment_id:Date.now(),warnings:[]};
   return{ok:true}},
 async put(u,b){await wait(60);return{ok:true,saved:(b&&b.marks||[]).length}},
 async del(u){await wait(60);return{ok:true}},
 async req(m,u,b){return m==='GET'?this.get(u):m==='POST'?this.post(u,b):m==='PUT'?this.put(u,b):this.del(u)}};
})();
"""
DIST.mkdir(parents=True, exist_ok=True)
role_of = {"student": "student", "teacher": "faculty", "admin": "admin"}
for name, role in role_of.items():
    h = (WEB / f"{name}.html").read_text()
    js = MOCK.replace("__SNAP__", json.dumps({role: snap[role], "admin_students_all": snap["admin_students_all"]}, separators=(",", ":"))).replace("__ROLE__", role)
    h = h.replace("<script>", "<script>" + js + "</script>\n<script>", 1) if "<script>" in h else h
    h = re.sub(r"""location\.href\s*=\s*['"]/login['"]""", "location.href='index.html'", h)
    h = h.replace('href="/"', 'href="index.html"')
    (DIST / f"{name}.html").write_text(h)

# Landing page: pick a role (replaces the login screen in the static demo)
login = (WEB / "login.html").read_text()
login = re.sub(r"location\.href\s*=\s*j\.redirect", "location.href=j.redirect.replace('/','')+'.html'", login)
shim = """<script>
const MAP={akash:'student',khan:'teacher',admin:'admin'};
window.fetch=async(u,o)=>{const b=JSON.parse(o.body||'{}');const ok=({akash:'akash123',khan:'khan123',admin:'admin123'})[b.username]===b.password;
 const body=ok?{role:'x',redirect:'/'+MAP[b.username],name:b.username}:{error:'Invalid username or password.'};
 return{ok,status:ok?200:401,json:async()=>body}};
</script>
"""
login = login.replace("<script>", shim + "<script>", 1)
(DIST / "index.html").write_text(login)
print("built", [p.name for p in DIST.iterdir()], {k: len(v) for k, v in snap.items() if isinstance(v, dict)})
