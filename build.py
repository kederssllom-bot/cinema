#!/usr/bin/env python3
"""
شاهد الآن | WatchNow - مولّد الصفحات الثابتة

يقرأ جدول الأفلام (نفس الجدول اللي بيقرأه index.html) ويولّد:
  - صفحة ثابتة لكل فيلم:  f/<id>/index.html   (عشان جوجل يقدر يفهرسها)
  - sitemap.xml و robots.txt

بيشتغل تلقائيًا على GitHub Actions، وما بتحتاج تشغله بإيدك.
الإعدادات بتنقرا من index.html نفسه (SHEET_CSV_URL وروابط تيليجرام بالفوتر).

للتجربة المحلية:
  CSV_FILE=film.csv SITE_URL=https://example.com python3 build.py
"""
import csv, html, io, json, os, re, shutil, sys
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")
DEFAULT_SITE = "https://kederssllom-bot.github.io/cinema"
SITE_NAME = "شاهد الآن | WatchNow"

src = open(INDEX, encoding="utf-8").read()

_m = re.search(r'const\s+SHEET_CSV_URL\s*=\s*"([^"]*)"', src)
SHEET = os.environ.get("SHEET_URL") or (_m.group(1) if _m else "")
_m = re.search(r"https://t\.me/\+[\w-]+", src)
JOIN = _m.group(0) if _m else ""            # رابط القناة (اختياري، بس للفوتر)
_m = re.search(r"https://t\.me/(?!\+)\w+", src)
CONTACT = _m.group(0) if _m else ""         # رابط التواصل لطلبات الإزالة


def site_url():
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == owner.lower() + ".github.io":
            return "https://" + name
        return "https://%s.github.io/%s" % (owner.lower(), name)
    return DEFAULT_SITE


SITE = site_url()
e = html.escape


# ---------------------------------------------------------------- قراءة الجدول
def csv_url(u):
    """يحوّل رابط المشاركة العادي لرابط CSV (نفس منطق index.html)."""
    if not u or re.search(r"output=csv|tqx=out:csv", u, re.I) or "/spreadsheets/d/e/" in u:
        return u
    m = re.search(r"/spreadsheets/d/([\w-]+)", u)
    if not m:
        return u
    g = re.search(r"[#&?]gid=(\d+)", u)
    return "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv&headers=1%s" % (
        m.group(1), "&gid=" + g.group(1) if g else "")


def load_rows():
    local = os.environ.get("CSV_FILE")
    if local:
        text = open(local, encoding="utf-8-sig").read()
    else:
        if not SHEET:
            sys.exit("ما لقيت SHEET_CSV_URL بملف index.html")
        req = Request(csv_url(SHEET), headers={"User-Agent": "Mozilla/5.0"})
        text = urlopen(req, timeout=60).read().decode("utf-8-sig")
        if re.match(r"\s*<(!doctype|html)", text, re.I):
            sys.exit("الجدول مش منشور أو مش مشارك (رجع صفحة HTML بدل CSV)")
    rd = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in rd]


def pick(row, keys):
    """أول عمود فيه قيمة من هالأسماء (عربي أو إنجليزي)."""
    for k in keys:
        v = row.get(k.lower(), "")
        if v:
            return v
    return ""


# ---------------------------------------------------------------- تنظيف القيم
def poster_url(raw, big=False):
    u = (raw or "").strip()
    if not u:
        return ""
    m = re.search(r"drive\.google\.com/file/d/([\w-]+)", u) or \
        re.search(r"drive\.google\.com/(?:open|uc|thumbnail)\?[^#]*id=([\w-]+)", u)
    if m:
        return "https://lh3.googleusercontent.com/d/%s=w%d" % (m.group(1), 1000 if big else 600)
    if re.match(r"https?://", u, re.I):
        return u
    if re.match(r"^[\w./-]+\.(webp|jpg|jpeg|png|avif)$", u, re.I):
        return SITE + "/" + u.lstrip("./")      # مسار نسبي داخل المستودع
    return ""


def tg_url(raw):
    u = (raw or "").strip()
    if re.match(r"^(t\.me|telegram\.me)/", u, re.I):
        u = "https://" + u
    return u if re.match(r"^https?://(t|telegram)\.me/.+", u, re.I) else ""


def to_int(raw):
    t = (raw or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    m = re.search(r"\d+", t)
    return int(m.group(0)) if m else 0


def fmt_dur(n):
    if not n:
        return ""
    if n < 60:
        return "%d د" % n
    h, m = divmod(n, 60)
    return "%d س%s" % (h, (" %d د" % m) if m else "")


def films():
    out, used = [], set()
    for i, r in enumerate(load_rows()):
        title = pick(r, ["العنوان", "title"])
        if not title:
            continue
        link = tg_url(pick(r, ["رابط تيليجرام", "رابط", "link", "telegram"]))
        # رقم المنشور بالتيليجرام = معرّف ثابت ما بيتغير لو أضفت أفلام بنص الجدول
        m = re.search(r"/(\d+)/?(?:\?.*)?$", link)
        fid = m.group(1) if m else "m%d" % (i + 1)
        base, n = fid, 2
        while fid in used:
            fid = "%s-%d" % (base, n)
            n += 1
        used.add(fid)
        out.append(dict(
            id=fid,
            title=title,
            year=pick(r, ["السنة", "year"]),
            genres=[g.strip() for g in re.split(r"[،,|]", pick(r, ["التصنيف", "category"])) if g.strip()],
            desc=pick(r, ["الوصف", "description"]),
            poster=poster_url(pick(r, ["البوستر", "poster"])),
            poster_big=poster_url(pick(r, ["البوستر", "poster"]), big=True),
            link=link,
            license=pick(r, ["المصدر/الرخصة", "المصدر", "الرخصة", "license", "source"]),
            duration=to_int(pick(r, ["المدة", "المدة بالدقائق", "duration", "runtime"])),
        ))
    return out


# ---------------------------------------------------------------- القالب
CSS = """
*{box-sizing:border-box;margin:0}
html{-webkit-tap-highlight-color:transparent}
body{background:#0b0b0b;color:#f5f5f5;font-family:'Cairo',system-ui,sans-serif;line-height:1.7;min-height:100vh}
a{color:inherit}
.wrap{max-width:900px;margin:0 auto;padding:0 16px}
.hdr{position:sticky;top:0;z-index:5;background:rgba(11,11,11,.92);backdrop-filter:blur(12px);border-bottom:1px solid rgba(255,255,255,.08)}
.hdr .wrap{height:56px;display:flex;align-items:center}
.logo{font-size:24px;font-weight:900;color:#e50914;text-decoration:none}
.back{display:inline-block;margin:18px 0 8px;color:rgba(255,255,255,.6);font-size:14px;text-decoration:none}
.fgrid{display:grid;gap:22px;grid-template-columns:1fr;padding-bottom:30px}
@media(min-width:680px){.fgrid{grid-template-columns:260px 1fr;gap:34px}}
.poster{aspect-ratio:2/3;border-radius:10px;overflow:hidden;background:#141414;max-width:260px;width:100%;margin:0 auto;box-shadow:0 12px 32px rgba(0,0,0,.5)}
.poster img{width:100%;height:100%;object-fit:cover;display:block}
.fb{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:14px;background:linear-gradient(165deg,#1d1d1d,#0d0d0d)}
.fb b{font-size:18px}.fb small{color:rgba(255,255,255,.5)}
h1{font-size:28px;font-weight:900;line-height:1.35}
.line{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:6px;color:rgba(255,255,255,.65);font-size:14px}
.gen{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.gen span,.gen a{background:rgba(255,255,255,.1);border-radius:999px;padding:3px 13px;font-size:13px;text-decoration:none}
h4{margin:22px 0 6px;font-size:16px;font-weight:800}
.story{color:rgba(255,255,255,.85);font-size:15px;line-height:2}
.src{margin-top:14px;font-size:12px;color:rgba(255,255,255,.4)}
.cta{margin-top:22px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;background:#e50914;color:#fff;font-weight:800;font-size:16px;padding:13px 28px;border-radius:8px;text-decoration:none}
.btn:active{transform:scale(.97)}
.btn.grey{background:rgba(255,255,255,.12)}
.tgi{width:20px;height:20px;fill:currentColor}
footer{border-top:1px solid rgba(255,255,255,.1);padding:26px 16px;text-align:center;font-size:12px;color:rgba(255,255,255,.4)}
footer p+p{margin-top:4px}
footer a{text-decoration:underline}
"""

TG = ('<svg class="tgi" viewBox="0 0 24 24"><path d="M9.8 15.6 9.6 19c.4 0 .6-.2.8-.4l2-1.9 4.1 3c.8.4 1.3.2 '
      '1.5-.7l2.7-12.9c.3-1.2-.4-1.7-1.2-1.4L3.8 10.1c-1.1.4-1.1 1.1-.2 1.4l4.3 1.3 9.9-6.2c.5-.3.9-.1.5.2z"/></svg>')


def page(f, all_films):
    url = "%s/f/%s/" % (SITE, f["id"])
    title = "%s (%s) | %s" % (f["title"], f["year"], SITE_NAME) if f["year"] else "%s | %s" % (f["title"], SITE_NAME)
    desc = (f["desc"] or "%s - أرشيف أفلام من الملكية العامة على شاهد الآن" % f["title"]).replace("\n", " ")[:155]

    ld = {"@context": "https://schema.org", "@type": "Movie", "name": f["title"], "url": url}
    if f["desc"]:
        ld["description"] = f["desc"]
    if f["year"]:
        ld["datePublished"] = f["year"]
    if f["duration"]:
        ld["duration"] = "PT%dH%dM" % divmod(f["duration"], 60)
    if f["genres"]:
        ld["genre"] = f["genres"]
    if f["poster_big"]:
        ld["image"] = f["poster_big"]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

    meta = []
    if f["year"]:
        meta.append("<span>%s</span>" % e(f["year"]))
    if f["duration"]:
        meta.append("<span>%s</span>" % e(fmt_dur(f["duration"])))
    line = "".join(meta)
    gen = "".join("<span>%s</span>" % e(g) for g in f["genres"])

    related = [x for x in all_films if x["id"] != f["id"] and set(x["genres"]) & set(f["genres"])][:8]
    rel = ""
    if related:
        rel = '<h4>أفلام مشابهة</h4><div class="gen">%s</div>' % "".join(
            '<a href="../%s/">%s</a>' % (e(x["id"]), e(x["title"])) for x in related)

    img = ('<img src="%s" alt="%s" referrerpolicy="no-referrer" onerror="this.remove()">' % (e(f["poster"]), e(f["title"]))
           if f["poster"] else "")
    fb = '<div class="fb"><b>%s</b><small>%s</small></div>' % (e(f["title"]), e(f["year"]))
    og_img = '<meta property="og:image" content="%s">' % e(f["poster_big"]) if f["poster_big"] else ""

    watch = ('<a class="btn" href="%s" target="_blank" rel="noopener noreferrer">%sمشاهدة</a>' % (e(f["link"]), TG)
             if f["link"] else '<a class="btn grey" href="../../">كل الأفلام</a>')
    lic = '<p class="src">المصدر / الرخصة: %s</p>' % e(f["license"]) if f["license"] else ""

    foot = []
    if JOIN:
        foot.append('<p>تابع الجديد على <a href="%s" target="_blank" rel="noopener noreferrer">قناتنا على تيليجرام</a></p>' % e(JOIN))
    foot.append("<p>جميع المحتويات المعروضة من الملكية العامة أو برخص مفتوحة، والمصدر مذكور في كل عمل.</p>")
    if CONTACT:
        foot.append('<p>إذا كنت صاحب حقوق وترى أن عملاً ما لا يجب أن يظهر هنا، راسلنا عبر '
                    '<a href="%s" target="_blank" rel="noopener noreferrer">قناة تيليجرام</a> وسيُزال فوراً.</p>' % e(CONTACT))

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="video.movie">
<meta property="og:site_name" content="{e(SITE_NAME)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
{og_img}
<meta name="theme-color" content="#0b0b0b">
<link rel="icon" type="image/png" href="../../icons/icon-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>{CSS}</style>
<script type="application/ld+json">{ld_json}</script>
</head>
<body>
<header class="hdr"><div class="wrap"><a class="logo" href="../../">شاهد الآن</a></div></header>
<main class="wrap">
<a class="back" href="../../">← كل الأفلام</a>
<div class="fgrid">
<div><div class="poster">{img}{fb}</div></div>
<div>
<h1 dir="auto">{e(f["title"])}</h1>
<div class="line">{line}</div>
<div class="gen">{gen}</div>
<h4>القصة</h4>
<p class="story">{e(f["desc"]) or "لا يوجد وصف."}</p>
{lic}
<div class="cta">{watch}</div>
{rel}
</div>
</div>
</main>
<footer>{"".join(foot)}</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- التشغيل
def main():
    fl = films()
    if not fl:
        # ما نمسح الصفحات الموجودة إذا الجدول رجع فاضي (غالبًا خطأ مؤقت)
        sys.exit("الجدول رجع بدون أفلام - ما غيّرت شي")

    # نجهّز كل شي بالذاكرة أول، وبعدين نكتب، حتى لو صار خطأ ما نخرّب الموجود
    files = {os.path.join("f", f["id"], "index.html"): page(f, fl) for f in fl}
    urls = ["%s/" % SITE] + ["%s/f/%s/" % (SITE, f["id"]) for f in fl]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += ["<url><loc>%s</loc></url>" % e(u) for u in urls]   # بدون تاريخ: حتى ما يتغير الملف كل يوم
    sm.append("</urlset>")
    files["sitemap.xml"] = "\n".join(sm) + "\n"
    files["robots.txt"] = "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE

    shutil.rmtree(os.path.join(ROOT, "f"), ignore_errors=True)
    for rel_path, content in files.items():
        p = os.path.join(ROOT, rel_path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(content)
    print("تم: %d فيلم، %d رابط بالخريطة" % (len(fl), len(urls)))


if __name__ == "__main__":
    main()
