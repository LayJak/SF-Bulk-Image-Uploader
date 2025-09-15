# --- BEGIN cms_packager.py (refactor adds run_packager) ---
import argparse, os, json, re, zipfile, sys, datetime
from pathlib import Path
from collections import Counter, defaultdict

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")

def is_image_name(name: str) -> bool:
    return (not name.startswith("._")) and (os.path.splitext(name)[1].lower() in IMAGE_EXTS)

def analyze_filename(basename: str):
    problems = []
    stem = Path(basename).stem
    ext = Path(basename).suffix
    low_stem = stem.lower()
    base = stem
    category = "unknown"
    canonical = None

    if low_stem.endswith("_logo_rev"):
        category = "logo_rev"; base = stem[:-(len("_logo_rev"))]
        canonical = f"{base}_logo_rev.png"
        if not stem.endswith("_logo_rev"): problems.append("Suffix must be exactly '_logo_rev'.")
    elif low_stem.endswith("_logo_fullcolor"):
        category = "logo_fullcolor"; base = stem[:-(len("_logo_fullcolor"))]
        canonical = f"{base}_logo_fullcolor.png"
        if not stem.endswith("_logo_fullcolor"): problems.append("Suffix must be exactly '_logo_fullcolor'.")
    elif low_stem.endswith("_round"):
        category = "hs_round"; base = stem[:-(len("_round"))]
        canonical = f"{base}_round.png"
        if not stem.endswith("_round"): problems.append("Suffix must be exactly '_round'.")
    elif low_stem.endswith("_square"):
        category = "hs_square"; base = stem[:-(len("_square"))]
        canonical = f"{base}_square.png"
        if not stem.endswith("_square"): problems.append("Suffix must be exactly '_square'.")
    else:
        category = "hs_silhouette"; base = stem
        canonical = f"{base}.png"
        if re.search(r"_(round|square|logo_rev|logo_fullcolor|silhouette)$", low_stem):
            problems.append("Silhouette must have no suffix; use 'Agent Name.png'.")

    if ext.lower() != ".png":
        problems.append("Extension must be .png (actual file must be PNG).")
    elif ext != ".png":
        problems.append("Extension must be lowercase '.png'.")

    return {
        "category": category,
        "base": base.strip(),
        "canonical": canonical,
        "problems": problems
    }

def title_from_category(base: str, category: str) -> str:
    if category == "hs_round":       return f"{base} (Round Headshot)"
    if category == "hs_square":      return f"{base} (Square Headshot)"
    if category == "hs_silhouette":  return f"{base} (Silhouette Headshot)"
    if category == "logo_rev":       return f"{base} (Logo - Reversed)"
    if category == "logo_fullcolor": return f"{base} (Logo - Full Color)"
    return f"{base} (Image)"

def _build_stats_text(items, file_map, totals, naming):
    from collections import Counter
    ext_counts = Counter(Path(a).suffix.lower() for _,_,a in file_map)
    lines = []
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines += [
        "Salesforce CMS Packager - STATS",
        f"Generated: {ts}",
        f"Input Folder: {totals['input_dir']}",
        f"Output ZIP:   {totals['zip_path']}",
        "",
        "FILE SCAN",
        f"  Total files scanned:   {totals['total_files']}",
        f"  Images processed:      {totals['image_files']}",
        f"  Non-images ignored:    {totals['non_images']}",
        f"  Dot-underscore ignored:{totals['dot_underscore']}",
        "",
        "IMAGE EXTENSIONS",
    ]
    for ext, cnt in sorted(ext_counts.items()):
        lines.append(f"  {ext or '[none]'}: {cnt}")
    lines += [
        "",
        "NAMING COMPLIANCE",
        f"  Compliant:             {naming['compliant_count']}",
        f"  Auto-renamed:          {naming['auto_renamed_count']}",
        f"  Violations:            {len(naming['violations'])}",
    ]
    if naming['violations'][:10]:
        lines.append("  First issues:")
        for v in naming['violations'][:10]:
            lines.append(f"    - {v}")
    if naming['renamed'][:10]:
        lines.append("  First auto-renames:")
        for old, new in naming['renamed'][:10]:
            lines.append(f"    - {old}  =>  {new}")
    lines += [
        "",
        "MANIFEST SUMMARY (Classic CMS)",
        f"  Total manifest items:  {len(items)}",
        "",
        "SAMPLE (first 10 items)",
    ]
    for item, _, _ in file_map[:10]:
        lines.append(f"  - {item['body']['title']}  ->  _media/{item['body']['source']['ref']}")
    lines.append("")
    return "\n".join(lines)

def run_packager(input_dir, out_zip, stats_path, title_suffix=""):
    """Core function used by GUI and CLI. Raises RuntimeError on fatal problems."""
    input_dir = Path(input_dir)
    if not input_dir.exists():
        raise RuntimeError(f"Input folder not found: {input_dir}")

    # Scan
    total_files = non_images = dot_underscore = 0
    disk_files = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            total_files += 1
            full = os.path.join(root, f)
            name = os.path.basename(full)
            if name.startswith("._"):
                dot_underscore += 1; continue
            if is_image_name(name):
                disk_files.append(full)
            else:
                non_images += 1
    if not disk_files:
        raise RuntimeError("No image files found.")

    # Analyze naming
    analyses = []
    violations = []
    for full in sorted(disk_files):
        base = os.path.basename(full)
        info = analyze_filename(base)
        analyses.append((full, base, info))

        hard = [p for p in info["problems"] if "Extension must be .png" in p or "Silhouette must have no suffix" in p]
        soft = [p for p in info["problems"] if p not in hard]
        if hard:
            violations.append(f"{base}  ->  {'; '.join(hard)}  (expected like: {info['canonical']})")
        if soft:
            # we auto-fix case-only differences inside the ZIP
            pass
    if violations:
        raise RuntimeError("Naming violations:\n" + "\n".join("  - " + v for v in violations))

    # Choose final arcnames (auto-fix case/extension case only)
    renamed = []
    final_entries = []
    for full, base, info in analyses:
        arc = info["canonical"]
        if arc != base:
            renamed.append((base, arc))
        # normalize .PNG -> .png if needed
        if Path(arc).suffix != ".png" and Path(arc).suffix.lower() == ".png":
            arc = str(Path(arc).with_suffix(".png"))
        final_entries.append((full, arc, info))

    # De-dupe any collisions
    from collections import Counter, defaultdict
    counts = Counter(a for _, a, _ in final_entries)
    used = defaultdict(int)
    de_dup_entries = []
    for full, arc, info in final_entries:
        if counts[arc] > 1:
            idx = used[arc]
            if idx > 0:
                root, ext = os.path.splitext(arc)
                arc = f"{root}_{idx}{ext}"
            used[arc] += 1
        de_dup_entries.append((full, arc, info))

    # Build CMS items
    items = []
    file_map = []
    for full, arc, info in de_dup_entries:
        title = title_from_category(info["base"], info["category"])
        if title_suffix:
            title = f"{title} {title_suffix}".strip()
        items.append({
            "type": "cms_image",
            "urlName": slugify(title),
            "status": "Draft",
            "body": {
                "title": title,
                "altText": title,
                "source": {"ref": arc}
            }
        })
        file_map.append((items[-1], full, arc))

    payload = {"content": items}

    # Write ZIP
    zpath = Path(out_zip)
    zpath.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(payload, indent=2))
        for _, full, arc in file_map:
            z.write(full, os.path.join("_media", arc))

    # Write STATS
    totals = {
        "input_dir": str(input_dir),
        "zip_path": str(zpath),
        "total_files": total_files,
        "image_files": len(disk_files),
        "non_images": non_images,
        "dot_underscore": dot_underscore,
    }
    naming = {
        "compliant_count": sum(1 for _,_,i in analyses if not i["problems"]),
        "auto_renamed_count": len(renamed),
        "violations": [],
        "renamed": renamed
    }
    stats_path = Path(stats_path) if stats_path else zpath.with_name(zpath.stem + "_STATS.txt")
    stats_path.write_text(_build_stats_text(items, file_map, totals, naming), encoding="utf-8")
    return str(zpath), str(stats_path)

def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--zip", required=True)
    ap.add_argument("--stats", default=None)
    ap.add_argument("--title-suffix", default="")
    args = ap.parse_args()
    try:
        z, s = run_packager(args.input, args.zip, args.stats, args.title_suffix)
        print(f"Wrote ZIP: {z}")
        print(f"Wrote STATS: {s}")
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    _cli()
# --- END cms_packager.py ---
