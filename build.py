#!/usr/bin/env python3
"""
يقرأ جدول الأفلام ويولّد:
  - صفحة ثابتة لكل فيلم:  f/<id>/index.html   (عشان جوجل يقدر يفهرسها)
  - sitemap.xml و robots.txt
بيشتغل تلقائيًا على GitHub Actions، وما بتحتاج تشغله بإيدك.
الإعدادات (القناة ورابط الجدول) بتنقرا من CONFIG جوا index.html.
"""
import csv, html, io, json, os, re, shutil, sys, datetime
from urllib.request import Request, urlopen

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(ROOT, "index.html")
src = open(INDEX, encoding="utf-8").read()

channel = re.search(r'channel:\s*"([^"]+)"', src).group(1)
sheet = re.search(r'sheetCsvUrl:\s*"([^"]*)"', src).group(1)
style = re.search(r"<style>(.*?)</style>", src, re.S).group(1)
JOIN = "https://t.me/" + channel


def site_url():
    if os.environ.get("SITE_URL"):
        return os.environ["SITE_URL"].rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/", 1)
        if name.lower() == owner.lower() + ".github.io":
            return "https://" + name
        return "https://%s.github.io/%s" % (owner, name)
    sys.exit("حدد SITE_URL (مثال: https://اسمك.github.io/cinema)")


SITE = site_url()


def csv_url(u):
    m = re.search(r"/spreadsheets/d/([\w-]+)", u)
    if m and "/d/e/" not in u and "output=csv" not in u:
        return "https://docs.google.com/spreadsheets/d/%s/gviz/tq?tqx=out:csv" % m.group(1)
    return u


def load_rows():
    local = os.environ.get("CSV_FILE")  # للتجربة المحلية فقط
    if local:
        text = open(local, encoding="utf-8-sig").read()
    else:
        if not sheet:
            sys.exit("ما في sheetCsvUrl بملف index.html")
        req = Request(csv_url(sheet), headers={"User-Agent": "Mozilla/5.0"})
        text = urlopen(req, timeout=60).read().decode("utf-8-sig")
    rd = csv.DictReader(io.StringIO(text))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in rd]


def fix_image(u):
    u = (u or "").strip()
    m = re.search(r"drive\.google\.com/(?:file/d/|open\?id=|uc\?(?:export=\w+&)?id=)([\w-]+)", u)
    return "https://drive.google.com/thumbnail?id=%s&sz=w600" % m.group(1) if m else u


def films():
    out = []
    for i, r in enumerate(load_rows()):
        title = re.sub(r"\s*\((?:19|20)\d{2}\)\s*$", "", r.get("title", "")).strip()
        if not title:
            continue
        link = r.get("link", "").strip()
        m = re.search(r"/(\d+)/?(?:\?.*)?$", link)
        try:
            dur = int(r.get("duration", "") or 0)
        except ValueError:
            dur = 0
        out.append(dict(
            id=m.group(1) if m else "r%d" % (i + 1),
            title=title,
            year=r.get("year", ""),
            duration=dur,
            genres=[g.strip() for g in re.split(r"[,،]", r.get("genre", "")) if g.strip()],
            story=r.get("story", ""),
            link=link or JOIN,
            poster=fix_image(r.get("poster", "")),
        ))
    return out


e = html.escape


def fmt_dur(m):
    if not m:
        return ""
    h, mm = divmod(m, 60)
    return ((("%d س " % h) if h else "") + (("%d د" % mm) if mm else "")).strip()


TG = ('<svg class="tgi" viewBox="0 0 24 24"><path d="M9.8 15.6 9.6 19c.4 0 .6-.2.8-.4l2-1.9 4.1 3c.8.4 1.3.2 '
      '1.5-.7l2.7-12.9c.3-1.2-.4-1.7-1.2-1.4L3.8 10.1c-1.1.4-1.1 1.1-.2 1.4l4.3 1.3 9.9-6.2c.5-.3.9-.1.5.2z"/></svg>')


def page(f, all_films):
    url = "%s/f/%s/" % (SITE, f["id"])
    desc = (f["story"] or "فيلم مترجم على Cinema").replace("\n", " ")[:155]
    title = "%s (%s) | Cinema أفلام مترجمة" % (f["title"], f["year"]) if f["year"] else "%s | Cinema أفلام مترجمة" % f["title"]
    ld = {"@context": "https://schema.org", "@type": "Movie", "name": f["title"], "description": f["story"], "url": url}
    if f["year"]:
        ld["datePublished"] = f["year"]
    if f["duration"]:
        ld["duration"] = "PT%dH%dM" % divmod(f["duration"], 60)
    if f["genres"]:
        ld["genre"] = f["genres"]
    if f["poster"]:
        ld["image"] = f["poster"]
    ld_json = json.dumps(ld, ensure_ascii=False).replace("</", "<\\/")

    meta = []
    if f["year"]:
        meta.append("<span>%s</span>" % e(f["year"]))
    if f["duration"]:
        meta.append("<span>%s</span>" % e(fmt_dur(f["duration"])))
    parts = meta + ['<span class="badge">ترجمة عربية</span>']
    line = '<i class="dot"></i>'.join(parts)

    gen = "".join("<span>%s</span>" % e(g) for g in f["genres"])
    related = [x for x in all_films if x["id"] != f["id"] and set(x["genres"]) & set(f["genres"])][:8]
    rel = ""
    if related:
        rel = '<h4>أفلام مشابهة</h4><div class="gen">%s</div>' % "".join(
            '<a href="../%s/"><span>%s</span></a>' % (e(x["id"]), e(x["title"])) for x in related)

    poster_inner = ""
    if f["poster"]:
        poster_inner = '<img src="%s" alt="%s" referrerpolicy="no-referrer" onerror="this.remove()">' % (e(f["poster"]), e(f["title"]))
    bg = ('style="background-image:url(\'%s\')"' % e(f["poster"])) if f["poster"] else ""
    h = sum(ord(c) * (31 ** i) for i, c in enumerate(reversed(f["title"]))) % 360
    fb = ('<div class="fb" style="background:linear-gradient(165deg,hsl(%d 38%% 17%%),hsl(%d 30%% 6%%))"><b>%s</b><small>%s</small></div>'
          % (h, (h + 30) % 360, e(f["title"]), e(f["year"])))
    og_img = '<meta property="og:image" content="%s">' % e(f["poster"]) if f["poster"] else ""

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="video.movie">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
{og_img}
<meta name="theme-color" content="#0b0b0b">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Tajawal:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>{style}</style>
<script type="application/ld+json">{ld_json}</script>
</head>
<body>
<header class="hdr solid"><div class="wrap">
<a class="logo" href="../../" aria-label="الصفحة الرئيسية"><b>CINEMA</b><span>أفلام<br>مترجمة</span></a>
<a class="btn btn-join" href="{e(JOIN)}" target="_blank" rel="noopener">{TG}انضم للقناة</a>
</div></header>
<main><div class="fpage"><div class="fbg" {bg}></div>
<div class="wrap film">
<a class="back" href="../../">→ كل الأفلام</a>
<div class="fgrid">
<div class="fposter"><div class="poster">{poster_inner}{fb}</div></div>
<div class="finfo">
<h1 dir="auto">{e(f["title"])}</h1>
<div class="line">{line}</div>
<div class="gen">{gen}</div>
<h4>قصة الفيلم</h4>
<p class="story">{e(f["story"]) or "—"}</p>
<div class="note">الفيلم بصوته الأصلي الإنجليزي مع ترجمة عربية.</div>
<div class="cta">
<a class="btn btn-play" href="{e(f["link"])}" target="_blank" rel="noopener">{TG}شاهد على تيليجرام</a>
<a class="btn btn-grey" style="height:50px" href="{e(JOIN)}" target="_blank" rel="noopener">انضم للقناة</a>
<small>الضغط على الزر بيفتح الفيلم مباشرة بقناتنا على تيليجرام</small>
</div>
{rel}
</div></div></div></div></main>
<footer><div class="wrap"><p>تابع كل الأفلام الجديدة أول بأول على <a href="{e(JOIN)}" target="_blank" rel="noopener">قناتنا على تيليجرام</a></p></div></footer>
</body>
</html>
"""


def main():
    fl = films()
    out = os.path.join(ROOT, "f")
    shutil.rmtree(out, ignore_errors=True)
    for f in fl:
        d = os.path.join(out, f["id"])
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "index.html"), "w", encoding="utf-8").write(page(f, fl))

    today = datetime.date.today().isoformat()
    urls = ["%s/" % SITE] + ["%s/f/%s/" % (SITE, f["id"]) for f in fl]
    sm = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sm += ["<url><loc>%s</loc><lastmod>%s</lastmod></url>" % (e(u), today) for u in urls]
    sm.append("</urlset>")
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(sm) + "\n")
    open(os.path.join(ROOT, "robots.txt"), "w", encoding="utf-8").write(
        "User-agent: *\nAllow: /\n\nSitemap: %s/sitemap.xml\n" % SITE)
    print("تم: %d فيلم، %d رابط بالخريطة" % (len(fl), len(urls)))


if __name__ == "__main__":
    main()
