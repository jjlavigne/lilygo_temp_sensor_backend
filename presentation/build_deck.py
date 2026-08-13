"""
Generate the Fleet Temperature Monitoring pitch deck as a .pptx.

Upload the output to Google Drive and open with Google Slides -- it imports as
fully editable slides, not images.

Numbers marked [EXAMPLE] use a worked scenario of 4 sites x 5 sensors. Replace
with Plymouth's real counts before presenting; the cost story is far stronger
with actual figures.
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

# --- Design tokens ------------------------------------------------------------
INK      = RGBColor(0x16, 0x23, 0x2B)   # near-black, slight blue bias
MUTED    = RGBColor(0x6B, 0x7C, 0x85)
FAINT    = RGBColor(0xA8, 0xB4, 0xBA)
ACCENT   = RGBColor(0x0E, 0x7C, 0x86)   # teal - our system
CONTRAST = RGBColor(0xB4, 0x54, 0x1F)   # rust - incumbent / cost
GOOD     = RGBColor(0x2E, 0x7D, 0x5B)
BG       = RGBColor(0xFF, 0xFF, 0xFF)
BG_ALT   = RGBColor(0xF4, 0xF7, 0xF8)
LINE     = RGBColor(0xD8, 0xE1, 0xE4)

FONT = "Arial"

W, H = Inches(13.333), Inches(7.5)
M = Inches(0.85)                      # page margin


def new_deck():
    p = Presentation()
    p.slide_width, p.slide_height = W, H
    return p


def blank(prs, bg=BG):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = bg
    return s


def text(slide, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         line_spacing=1.0, space_after=0):
    """runs = [(string, size_pt, bold, color, space_before_pt), ...]"""
    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, (txt, size, bold, color, space_before) in enumerate(runs):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        para.line_spacing = line_spacing
        para.space_before = Pt(space_before)
        para.space_after = Pt(space_after)
        r = para.add_run()
        r.text = txt
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = FONT
    return box


def rule(slide, x, y, w, color=ACCENT, thick=Pt(3)):
    from pptx.enum.shapes import MSO_SHAPE
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, thick)
    bar.fill.solid(); bar.fill.fore_color.rgb = color
    bar.line.fill.background()
    bar.shadow.inherit = False
    return bar


def box(slide, x, y, w, h, fill=BG_ALT, border=None):
    from pptx.enum.shapes import MSO_SHAPE
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
    sh.fill.solid(); sh.fill.fore_color.rgb = fill
    if border:
        sh.line.color.rgb = border; sh.line.width = Pt(1.25)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    try:
        sh.adjustments[0] = 0.04
    except Exception:
        pass
    return sh


def notes(slide, txt):
    slide.notes_slide.notes_text_frame.text = txt


def page(slide, n):
    text(slide, W - Inches(1.1), H - Inches(0.6), Inches(0.5), Inches(0.3),
         [(str(n), 10, False, FAINT, 0)], align=PP_ALIGN.RIGHT)


def content_slide(prs, kicker, title, n):
    s = blank(prs)
    rule(s, M, Inches(0.75), Inches(0.9))
    text(s, M, Inches(0.95), Inches(11), Inches(0.35),
         [(kicker.upper(), 11, True, ACCENT, 0)])
    text(s, M, Inches(1.35), Inches(11.2), Inches(0.9),
         [(title, 34, True, INK, 0)])
    page(s, n)
    return s


prs = new_deck()
n = 0

# ============================== 1. TITLE =====================================
n += 1
s = blank(prs)
rule(s, M, Inches(2.5), Inches(1.4), ACCENT, Pt(4))
text(s, M, Inches(2.85), Inches(10.5), Inches(1.6),
     [("Fleet Temperature\nMonitoring", 52, True, INK, 0)], line_spacing=0.95)
text(s, M, Inches(4.6), Inches(9.5), Inches(0.9),
     [("A cold-chain monitoring system built in-house — "
       "real-time alerting, multi-site visibility, and a fraction of the cost.",
       17, False, MUTED, 0)], line_spacing=1.3)
text(s, M, Inches(6.3), Inches(9), Inches(0.4),
     [("Prepared for Plymouth  ·  Prototype demonstration", 12, False, FAINT, 0)])
notes(s, "Open by saying what this is: a working system, not a concept. "
         "The board on the table is live and publishing right now. "
         "Set expectation that they'll see it react to a real temperature change in a few minutes.")

# ============================== 2. PROBLEM ===================================
n += 1
s = content_slide(prs, "The problem", "A cold chain is only as good as its proof", n)
items = [
    ("Product loss is silent",
     "A freezer drifting out of range overnight is discovered the next morning — "
     "after the load is gone."),
    ("Gaps can't be explained",
     "When data stops arriving, was it a dead sensor, a network dropout, or a "
     "disconnected probe? Most systems can't tell you."),
    ("The bill scales with sites",
     "Every new location adds another subscription, another set of pre-calibrated "
     "sensors, another display."),
]
y = Inches(2.6)
for head, body in items:
    box(s, M, y, Inches(11.4), Inches(1.15), BG_ALT)
    text(s, M + Inches(0.35), y + Inches(0.18), Inches(10.8), Inches(0.3),
         [(head, 16, True, INK, 0)])
    text(s, M + Inches(0.35), y + Inches(0.55), Inches(10.7), Inches(0.45),
         [(body, 13, False, MUTED, 0)], line_spacing=1.25)
    y += Inches(1.35)
notes(s, "Keep this short — they already know the problem. "
         "The third point is the one to linger on: cost scales with sites, and that's what we fix.")

# ============================== 3. ARCHITECTURE ==============================
n += 1
s = content_slide(prs, "How it works", "Four jobs, cleanly separated", n)
stages = [
    ("Sensor", "Probe in the freezer.\nReports temperature\nand battery.", ACCENT),
    ("Broker", "Routes messages.\nAuthenticated,\ndecoupled.", ACCENT),
    ("Database", "Stores every\nplausible reading.\nPermanent record.", ACCENT),
    ("Dashboard\n& Alerts", "Judges what's wrong.\nNotifies the right\nteam on Slack.", CONTRAST),
]
bw, gap = Inches(2.5), Inches(0.45)
x = M
for i, (title, body, col) in enumerate(stages):
    box(s, x, Inches(2.75), bw, Inches(2.5), BG_ALT, col)
    text(s, x + Inches(0.25), Inches(2.98), bw - Inches(0.5), Inches(0.7),
         [(title, 17, True, col, 0)], line_spacing=1.0)
    text(s, x + Inches(0.25), Inches(3.85), bw - Inches(0.5), Inches(1.2),
         [(body, 12, False, MUTED, 0)], line_spacing=1.3)
    if i < 3:
        text(s, x + bw + Inches(0.06), Inches(3.85), gap, Inches(0.4),
             [("→", 20, True, FAINT, 0)], align=PP_ALIGN.CENTER)
    x += bw + gap
text(s, M, Inches(5.6), Inches(11.4), Inches(0.8),
     [("The sensor never decides what's an emergency. It reports; the system judges. "
       "That separation is what makes alerting reliable — and what lets one platform "
       "serve sites with completely different temperature requirements.",
       13, False, MUTED, 0)], line_spacing=1.35)
notes(s, "Don't go deep on tech. The point of this slide is that it's a normal, "
         "well-understood architecture — nothing exotic, nothing fragile. "
         "If asked: MQTT, PostgreSQL, Grafana. All industry standard, all open source.")

# ============================== 4. DEMO ======================================
n += 1
s = blank(prs, BG_ALT)
rule(s, M, Inches(1.4), Inches(0.9))
text(s, M, Inches(1.6), Inches(11), Inches(0.35), [("LIVE", 11, True, ACCENT, 0)])
text(s, M, Inches(2.0), Inches(9.5), Inches(1.0),
     [("Watch it work", 40, True, INK, 0)])
beats = [
    ("1", "Probe sits in chilled water", "Dashboard green. All sites nominal."),
    ("2", "Move it to hot water", "Temperature crosses the limit within seconds. "
                                   "Panel turns red. Slack fires."),
    ("3", "Unplug the probe", "System reports a sensor fault, then marks the unit "
                              "offline — it knows the difference."),
]
y = Inches(3.4)
for num, head, body in beats:
    box(s, M, y, Inches(0.62), Inches(0.62), ACCENT)
    text(s, M, y + Inches(0.13), Inches(0.62), Inches(0.4),
         [(num, 17, True, BG, 0)], align=PP_ALIGN.CENTER)
    text(s, M + Inches(0.95), y + Inches(0.02), Inches(4.6), Inches(0.35),
         [(head, 16, True, INK, 0)])
    text(s, M + Inches(5.7), y + Inches(0.04), Inches(6.0), Inches(0.6),
         [(body, 13, False, MUTED, 0)], line_spacing=1.25)
    y += Inches(1.0)
notes(s, "This is the moment that sells it. Rehearse it.\n\n"
         "IMPORTANT: start the probe in chilled water, not room air. At room "
         "temperature it already reads ~73F, well above the 42.8F produce ceiling, "
         "so the dashboard would open in alarm.\n\n"
         "Hot tap water (~130F) is dramatic enough and safer for the probe than boiling.")

# ============================== 5. ALERTING ==================================
n += 1
s = content_slide(prs, "Functionality", "Three alerts, not one", n)
alerts = [
    ("Temperature excursion", ACCENT,
     "Every unit judged against its own limits. Produce at 36–43°F and frozen "
     "goods at −9 to 0°F are both handled by one rule."),
    ("Sensor offline", CONTRAST,
     "A dead sensor sends nothing — so a temperature rule can never fire. "
     "This catches the silence. It is the failure that actually loses product."),
    ("Low battery", GOOD,
     "Early warning before a unit goes dark, so it's replaced on a schedule "
     "rather than discovered after a loss."),
]
y = Inches(2.6)
for head, col, body in alerts:
    box(s, M, y, Inches(11.4), Inches(1.25), BG, col)
    text(s, M + Inches(0.4), y + Inches(0.2), Inches(10.6), Inches(0.35),
         [(head, 17, True, col, 0)])
    text(s, M + Inches(0.4), y + Inches(0.62), Inches(10.5), Inches(0.5),
         [(body, 13, False, MUTED, 0)], line_spacing=1.25)
    y += Inches(1.45)
text(s, M, Inches(6.35), Inches(11.4), Inches(0.5),
     [("Alerts route to the right team automatically — grouped by company and site, "
       "delivered to Slack wherever the manager is.", 13, False, INK, 0)])
notes(s, "The middle one is the differentiator. Ask them: if a sensor dies tonight, "
         "how does your current system tell you? Many threshold-based systems simply "
         "don't — no data means no alert. That gap is where product gets lost.")

# ============================== 6. MULTI-SITE ================================
n += 1
s = content_slide(prs, "Scale", "One platform, every site", n)
text(s, M, Inches(2.5), Inches(11.4), Inches(0.6),
     [("Each site sees only its own equipment. Management sees everything.",
       17, False, INK, 0)])
cols = [
    ("Per-site view", "A manager opens their site and sees their units — "
                      "temperature, battery, last reading, current status."),
    ("Fleet view", "One screen across every site and every company, "
                   "filtered on demand."),
    ("Adding a site", "Register the devices. Dashboards and alerts pick it up "
                      "automatically — no new subscription, no new licence."),
]
x = M
for head, body in cols:
    box(s, x, Inches(3.4), Inches(3.6), Inches(2.2), BG_ALT)
    text(s, x + Inches(0.3), Inches(3.65), Inches(3.0), Inches(0.4),
         [(head, 16, True, ACCENT, 0)])
    text(s, x + Inches(0.3), Inches(4.15), Inches(3.05), Inches(1.4),
         [(body, 12.5, False, MUTED, 0)], line_spacing=1.3)
    x += Inches(3.9)
notes(s, "Emphasise the third column. With the incumbent, every new site is another "
         "$100/month forever. Here it's a configuration change with no marginal cost.")

# ============================== 7. HARDWARE COST =============================
n += 1
s = content_slide(prs, "Cost", "Hardware, per monitoring point", n)
rows = [
    ("", "SmartSense", "This system", ""),
    ("Sensor", "$125  pre-calibrated", "$25  sensor + board", ""),
    ("Wireless unit + display", "$245", "$35  incl. display", ""),
    ("Enclosure", "included", "$10  3D printed, custom", ""),
    ("Per point", "$370", "$70", "81% less"),
]
tw = Inches(11.4)
tbl = s.shapes.add_table(len(rows), 4, M, Inches(2.55), tw, Inches(2.9)).table
tbl.columns[0].width = Inches(3.4)
tbl.columns[1].width = Inches(3.1)
tbl.columns[2].width = Inches(3.2)
tbl.columns[3].width = Inches(1.7)
for ri, row in enumerate(rows):
    for ci, val in enumerate(row):
        c = tbl.cell(ri, ci)
        c.text = val
        c.margin_left = Inches(0.18); c.margin_top = Inches(0.09)
        c.vertical_anchor = MSO_ANCHOR.MIDDLE
        para = c.text_frame.paragraphs[0]
        r = para.runs[0] if para.runs else para.add_run()
        r.font.name = FONT
        last = (ri == len(rows) - 1)
        head = (ri == 0)
        r.font.size = Pt(15 if last else 13.5)
        r.font.bold = head or last
        if head:
            r.font.color.rgb = INK if ci == 0 else (CONTRAST if ci == 1 else ACCENT)
        elif last:
            r.font.color.rgb = INK if ci == 0 else (CONTRAST if ci == 1 else (ACCENT if ci == 2 else GOOD))
        else:
            r.font.color.rgb = MUTED if ci != 0 else INK
        c.fill.solid()
        c.fill.fore_color.rgb = BG_ALT if (head or last) else BG
text(s, M, Inches(5.75), Inches(11.4), Inches(0.8),
     [("Calibration is done in-house against a single NIST-traceable reference "
       "thermometer — one purchase of roughly $350 covers the whole fleet, instead of "
       "$125 built into every sensor forever.", 13, False, MUTED, 0)], line_spacing=1.35)
notes(s, "Have the calibration answer ready — it's the likeliest objection. "
         "Auditors under FSMA/HACCP want traceability, not just 'we checked it'. "
         "One NIST-traceable reference gives you that documentation trail for a few "
         "hundred dollars once. Say it before they ask.")

# ============================== 8. RECURRING COST ============================
n += 1
s = content_slide(prs, "Cost", "The recurring bill is where it compounds", n)
box(s, M, Inches(2.6), Inches(5.5), Inches(2.7), BG_ALT, CONTRAST)
text(s, M + Inches(0.4), Inches(2.9), Inches(4.7), Inches(0.4),
     [("SMARTSENSE", 12, True, CONTRAST, 0)])
text(s, M + Inches(0.4), Inches(3.4), Inches(4.7), Inches(0.9),
     [("$100", 46, True, INK, 0), ("per month, per site", 14, False, MUTED, 4)])
text(s, M + Inches(0.4), Inches(4.55), Inches(4.7), Inches(0.6),
     [("Every new location adds another subscription. Cost grows with the business.",
       12.5, False, MUTED, 0)], line_spacing=1.25)

box(s, M + Inches(5.9), Inches(2.6), Inches(5.5), Inches(2.7), BG_ALT, ACCENT)
text(s, M + Inches(6.3), Inches(2.9), Inches(4.7), Inches(0.4),
     [("THIS SYSTEM", 12, True, ACCENT, 0)])
text(s, M + Inches(6.3), Inches(3.4), Inches(4.7), Inches(0.9),
     [("~$12", 46, True, INK, 0), ("per month, all sites", 14, False, MUTED, 4)])
text(s, M + Inches(6.3), Inches(4.55), Inches(4.7), Inches(0.6),
     [("Cloud server, database and dashboards. Slack alerting is free. "
       "Adding sites costs nothing.", 12.5, False, MUTED, 0)], line_spacing=1.25)

text(s, M, Inches(5.75), Inches(11.4), Inches(0.9),
     [("[EXAMPLE — replace with real site count]  At four sites: "
       "$4,800/year becomes roughly $144/year.", 15, True, INK, 0)])
notes(s, "REPLACE THE EXAMPLE with Plymouth's actual site count before presenting. "
         "The real number is far more persuasive than a hypothetical.\n\n"
         "Hosting is a small cloud server running the whole stack. Storage is "
         "negligible — 20 sensors generate about 350 MB a year.")

# ============================== 9. FIVE YEAR =================================
n += 1
s = blank(prs, INK)
text(s, M, Inches(1.5), Inches(11), Inches(0.4),
     [("[EXAMPLE] FIVE-YEAR TOTAL COST OF OWNERSHIP  ·  4 SITES, 20 MONITORING POINTS",
       12, True, RGBColor(0x7E, 0xC8, 0xD0), 0)])
text(s, M, Inches(2.3), Inches(5.2), Inches(2.2),
     [("$31,400", 60, True, RGBColor(0xE5, 0x8B, 0x52), 0),
      ("SmartSense", 17, False, RGBColor(0xB9, 0xC6, 0xCC), 8),
      ("$7,400 hardware + $24,000 subscriptions", 12.5,
       False, RGBColor(0x86, 0x98, 0xA0), 6)])
text(s, M + Inches(6.1), Inches(2.3), Inches(5.2), Inches(2.2),
     [("$2,470", 60, True, RGBColor(0x7E, 0xC8, 0xD0), 0),
      ("This system", 17, False, RGBColor(0xB9, 0xC6, 0xCC), 8),
      ("$1,400 hardware + $350 calibration reference + $720 hosting", 12.5,
       False, RGBColor(0x86, 0x98, 0xA0), 6)])
rule(s, M, Inches(5.15), Inches(11.4), RGBColor(0x2E, 0x40, 0x48), Pt(1))
text(s, M, Inches(5.5), Inches(11.4), Inches(1.0),
     [("Roughly $29,000 saved — and the gap widens with every site added.",
       26, True, BG, 0)])
notes(s, "This is the slide they'll remember. Say the number out loud, then stop talking.\n\n"
         "Recalculate with real site counts. If Plymouth has more than four sites the "
         "number gets dramatically better, because their cost is per-site and ours isn't.")

# ============================== 10. DEPLOYMENT ===============================
n += 1
s = content_slide(prs, "Deployment", "Two configurations, one system", n)
cfgs = [
    ("Fixed sites — warehouse freezers", ACCENT,
     "Mains powered, mounted outside the unit. A flat gasket-safe probe cable passes "
     "through the door seal — no drilling, no compromise to the seal. Reports "
     "continuously over WiFi.",
     "No batteries to manage. Lithium cells lose 20–40% of capacity at freezer "
     "temperatures, so mains is the correct choice wherever power exists."),
    ("In transit — trailers", CONTRAST,
     "Battery powered with scheduled wake-ups, reporting hourly over cellular. "
     "Same firmware, same platform — one setting differs.",
     "Months of battery life at an hourly reporting interval."),
]
y = Inches(2.55)
for head, col, body, note in cfgs:
    box(s, M, y, Inches(11.4), Inches(1.95), BG_ALT, col)
    text(s, M + Inches(0.4), y + Inches(0.22), Inches(10.6), Inches(0.35),
         [(head, 17, True, col, 0)])
    text(s, M + Inches(0.4), y + Inches(0.68), Inches(10.5), Inches(0.6),
         [(body, 13, False, MUTED, 0)], line_spacing=1.25)
    text(s, M + Inches(0.4), y + Inches(1.45), Inches(10.5), Inches(0.4),
         [(note, 12, True, INK, 0)], line_spacing=1.2)
    y += Inches(2.2)
notes(s, "The gasket-cable point matters — facilities teams worry about drilling into "
         "freezer walls. Flat probe cables designed to pass through door seals are "
         "standard practice and require no modification to the unit.")

# ============================== 11. RISKS ====================================
n += 1
s = content_slide(prs, "Honest assessment", "What we still need to solve", n)
risks = [
    ("Sensor accuracy at freezer temperatures",
     "The current probe is rated ±0.5°C only above −10°C. For frozen goods we move to "
     "an RTD probe — ±0.15°C across the full range, roughly $8–15 per unit."),
    ("Calibration traceability",
     "In-house calibration against one NIST-traceable reference gives auditable "
     "documentation. One purchase, not a per-sensor cost."),
    ("Security hardening",
     "The prototype runs on a trusted network. Production adds encrypted transport "
     "and per-device credentials before any customer data is carried."),
]
y = Inches(2.6)
for head, body in risks:
    text(s, M, y, Inches(11.4), Inches(0.35), [(head, 16, True, INK, 0)])
    text(s, M, y + Inches(0.42), Inches(11.2), Inches(0.6),
         [(body, 13, False, MUTED, 0)], line_spacing=1.3)
    rule(s, M, y + Inches(1.12), Inches(11.4), LINE, Pt(1))
    y += Inches(1.42)
text(s, M, Inches(6.5), Inches(11.4), Inches(0.5),
     [("None of these are blockers. All are understood, costed, and scheduled.",
       14, True, ACCENT, 0)])
notes(s, "Including this slide builds credibility. A pitch with no acknowledged "
         "weaknesses reads as naive. Raising these before they do shows you've "
         "actually engineered it rather than demoed it.")

# ============================== 12. NEXT STEPS ===============================
n += 1
s = content_slide(prs, "Next", "What it takes to go live", n)
steps = [
    ("1", "Pilot at one site", "Install alongside the existing system and run both "
                               "in parallel for 30 days. No risk, direct comparison."),
    ("2", "Validate and calibrate", "Calibrate the fleet against the reference "
                                    "thermometer and document the results for audit."),
    ("3", "Migrate site by site", "Each site moves when its pilot data is accepted. "
                                  "Subscriptions cancel as sites come across."),
]
y = Inches(2.65)
for num, head, body in steps:
    box(s, M, y, Inches(0.68), Inches(0.68), ACCENT)
    text(s, M, y + Inches(0.15), Inches(0.68), Inches(0.4),
         [(num, 18, True, BG, 0)], align=PP_ALIGN.CENTER)
    text(s, M + Inches(1.05), y + Inches(0.02), Inches(4.3), Inches(0.4),
         [(head, 17, True, INK, 0)])
    text(s, M + Inches(5.5), y + Inches(0.05), Inches(6.2), Inches(0.7),
         [(body, 13, False, MUTED, 0)], line_spacing=1.25)
    y += Inches(1.15)
box(s, M, Inches(6.15), Inches(11.4), Inches(0.85), BG_ALT, ACCENT)
text(s, M + Inches(0.4), Inches(6.36), Inches(10.6), Inches(0.45),
     [("Running one site in parallel costs a few hundred dollars in hardware and "
       "proves the entire case with real data.", 15, True, INK, 0)])
notes(s, "Close by asking for the pilot, not the contract. It's a small, low-risk "
         "yes — and running both systems side by side produces the evidence that "
         "makes the rest of the decision straightforward.")

out = r"C:\Users\julia.lavigne\fleet-telemetry-pipeline\presentation\Fleet-Temperature-Monitoring.pptx"
prs.save(out)
print(f"saved: {out}")
print(f"slides: {len(prs.slides.__iter__.__self__._sldIdLst)}")
