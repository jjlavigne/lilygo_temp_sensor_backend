"""
Generate the Fleet Temperature Monitoring pitch deck as a .pptx.

Upload to Google Drive, open with Google Slides -- imports as editable slides.

Design: dark slides carry the three moments (open, cost, ask); light slides carry
the substance. Georgia for display, Arial for body. Cold-to-warm accent pair
borrowed from the subject itself.

Voice: first person, plain, concrete. No corporate padding.

Capability claims about SmartSense are framed as questions to ask, not assertions
-- their pricing is known, their feature set is not.
"""
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# ---- tokens ----
DARK    = RGBColor(0x0F, 0x1B, 0x22)
DARK2   = RGBColor(0x1A, 0x2A, 0x33)
PAPER   = RGBColor(0xFA, 0xFB, 0xFC)
PANEL   = RGBColor(0xF0, 0xF4, 0xF5)
INK     = RGBColor(0x12, 0x1E, 0x25)
MUTED   = RGBColor(0x63, 0x77, 0x82)
FAINT   = RGBColor(0x9E, 0xAF, 0xB7)
COLD    = RGBColor(0x2B, 0x8A, 0x9E)
COLD_LT = RGBColor(0x7F, 0xC4, 0xD2)
WARM    = RGBColor(0xC4, 0x62, 0x2D)
WARM_LT = RGBColor(0xE8, 0x93, 0x5C)
GOOD    = RGBColor(0x2E, 0x7D, 0x5B)
HAIR    = RGBColor(0xDD, 0xE5, 0xE8)
HAIR_D  = RGBColor(0x2A, 0x3A, 0x44)

DISPLAY = "Georgia"
BODY    = "Arial"

W, H = Inches(13.333), Inches(7.5)
M     = Inches(0.9)
CW    = W - 2 * M          # content width


def deck():
    p = Presentation(); p.slide_width, p.slide_height = W, H; return p


def slide(prs, bg=PAPER):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = bg
    return s


def tx(s, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, ls=1.0):
    b = s.shapes.add_textbox(x, y, w, h); f = b.text_frame
    f.word_wrap = True; f.vertical_anchor = anchor
    f.margin_left = f.margin_right = f.margin_top = f.margin_bottom = 0
    for i, r in enumerate(runs):
        txt, size, bold, col, sb = r[0], r[1], r[2], r[3], (r[4] if len(r) > 4 else 0)
        font = r[5] if len(r) > 5 else BODY
        p = f.paragraphs[0] if i == 0 else f.add_paragraph()
        p.alignment = align; p.line_spacing = ls
        p.space_before = Pt(sb); p.space_after = Pt(0)
        run = p.add_run(); run.text = txt
        run.font.size = Pt(size); run.font.bold = bold
        run.font.color.rgb = col; run.font.name = font
    return b


def rect(s, x, y, w, h, fill=None, line=None, lw=Pt(1), rounded=False):
    sh = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
                            x, y, w, h)
    if fill is not None:
        sh.fill.solid(); sh.fill.fore_color.rgb = fill
    else:
        sh.fill.background()
    if line is not None:
        sh.line.color.rgb = line; sh.line.width = lw
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    if rounded:
        try: sh.adjustments[0] = 0.03
        except Exception: pass
    return sh


def notes(s, t): s.notes_slide.notes_text_frame.text = t


def header(s, num, kicker, title, dark=False):
    """Numbered section header used on every content slide."""
    ink   = PAPER if dark else INK
    muted = FAINT if dark else MUTED
    rect(s, M, Inches(0.72), Inches(0.055), Inches(0.42), COLD)
    tx(s, M + Inches(0.22), Inches(0.72), Inches(6), Inches(0.3),
       [(f"{num:02d}", 12, True, COLD, 0), ("   " + kicker.upper(), 12, False, muted, 0)])
    tx(s, M, Inches(1.28), CW, Inches(0.95),
       [(title, 33, False, ink, 0, DISPLAY)], ls=1.05)


def foot(s, txt, dark=False):
    tx(s, M, H - Inches(0.72), CW, Inches(0.32),
       [(txt, 10.5, False, HAIR_D if dark else FAINT, 0)])


prs = deck()

# ══════════════════════════ 1 · TITLE ══════════════════════════
s = slide(prs, DARK)
# cold-to-warm gradient motif, drawn as discrete bars
x = M
for i, c in enumerate([COLD, COLD, COLD_LT, WARM_LT, WARM, WARM]):
    rect(s, x, Inches(2.15), Inches(0.62), Inches(0.09), c)
    x += Inches(0.72)
tx(s, M, Inches(2.6), Inches(10.6), Inches(2.0),
   [("Temperature monitoring,", 46, False, PAPER, 0, DISPLAY),
    ("built in-house", 46, False, COLD_LT, 0, DISPLAY)], ls=1.08)
tx(s, M, Inches(4.75), Inches(9.4), Inches(1.0),
   [("Same job as SmartSense. Roughly a tenth of the cost.", 18, False, RGBColor(0xC3, 0xD2, 0xD8), 0)],
   ls=1.35)
tx(s, M, Inches(5.35), Inches(9.4), Inches(0.5),
   [("The unit on the table is live and reporting right now.", 18, True, PAPER, 0)])
rect(s, M, Inches(6.25), Inches(2.2), Inches(0.02), HAIR_D)
tx(s, M, Inches(6.5), Inches(9), Inches(0.35),
   [("Prototype demonstration  ·  Plymouth", 11, False, RGBColor(0x6E, 0x82, 0x8C), 0)])
notes(s, "Open with the object, not the slide. Pick up the board.\n\n"
         "'This has been running for six days. Everything you're about to see on screen "
         "is coming from it, or from twenty simulated units I built to prove it scales.'\n\n"
         "Don't explain the architecture yet. Get them looking at the hardware.")

# ══════════════════════════ 2 · WHAT I BUILT ══════════════════════════
s = slide(prs)
header(s, 1, "The system", "It already works. Here's what's running.")
stats = [
    ("21", "sensors reporting", "across 4 companies and 5 sites"),
    ("< 20s", "breach to Slack", "from probe to phone"),
    ("$70", "per monitoring point", "hardware, case and all"),
    ("0", "per-site licences", "adding a site costs nothing"),
]
bw = (CW - Inches(0.75)) / 4
x = M
for big, lab, sub in stats:
    tx(s, x, Inches(2.5), bw, Inches(0.8), [(big, 40, False, COLD, 0, DISPLAY)])
    tx(s, x, Inches(3.25), bw - Inches(0.2), Inches(0.28), [(lab, 13, True, INK, 0)])
    tx(s, x, Inches(3.56), bw - Inches(0.25), Inches(0.5), [(sub, 11.5, False, MUTED, 0)], ls=1.25)
    x += bw + Inches(0.25)

rect(s, M, Inches(4.35), CW, Inches(0.015), HAIR)

flow = [("Probe", "in the freezer"), ("Broker", "authenticated"),
        ("Database", "permanent record"), ("Dashboard", "judges + alerts")]
bw2 = (CW - Inches(1.2)) / 4
x = M
for i, (t, sub) in enumerate(flow):
    rect(s, x, Inches(4.75), bw2, Inches(1.05), PANEL, rounded=True)
    tx(s, x + Inches(0.25), Inches(4.95), bw2 - Inches(0.4), Inches(0.3),
       [(t, 14.5, True, INK, 0)])
    tx(s, x + Inches(0.25), Inches(5.28), bw2 - Inches(0.4), Inches(0.3),
       [(sub, 11.5, False, MUTED, 0)])
    if i < 3:
        tx(s, x + bw2, Inches(5.05), Inches(0.4), Inches(0.3),
           [("→", 16, False, FAINT, 0)], align=PP_ALIGN.CENTER)
    x += bw2 + Inches(0.4)

tx(s, M, Inches(6.15), CW, Inches(0.75),
   [("The probe never decides what counts as an emergency. It reports, the system judges. "
     "That's why one platform can watch produce at 40°F and a freezer at −5°F without "
     "either one getting the other's rules.", 13, False, MUTED, 0)], ls=1.35)
foot(s, "Built on PostgreSQL, MQTT and Grafana — all open source, all industry standard.")
notes(s, "Four numbers, then move on. Don't read them out — let them read.\n\n"
         "The bottom line is the one that matters technically: separating 'report' from "
         "'judge' is what lets one system serve customers with completely different "
         "temperature requirements. It's also why the alerting actually works.\n\n"
         "If asked what it's built on: nothing exotic. Postgres, MQTT, Grafana. "
         "No vendor lock-in, no proprietary anything.")

# ══════════════════════════ 3 · DEMO ══════════════════════════
s = slide(prs, DARK)
header(s, 2, "Live", "Watch it work", dark=True)
beats = [
    ("Chilled water", "Everything green.", COLD_LT),
    ("Hot water", "Crosses the limit in seconds. Panel goes red, Slack fires.", WARM_LT),
    ("Pull the probe out", "Reports a sensor fault, then marks the unit offline.\n"
                           "It knows the difference between broken and disconnected.", WARM),
]
y = Inches(2.75)
for i, (head, body, col) in enumerate(beats):
    rect(s, M, y + Inches(0.08), Inches(0.05), Inches(0.62), col)
    tx(s, M + Inches(0.35), y, Inches(3.6), Inches(0.4), [(head, 20, False, PAPER, 0, DISPLAY)])
    tx(s, M + Inches(4.3), y + Inches(0.04), Inches(7.0), Inches(0.8),
       [(body, 14, False, RGBColor(0xB4, 0xC5, 0xCC), 0)], ls=1.35)
    y += Inches(1.25)
rect(s, M, Inches(6.35), CW, Inches(0.015), HAIR_D)
tx(s, M, Inches(6.6), CW, Inches(0.4),
   [("Every number on screen is real. Nothing here is a mock-up.", 13, True, COLD_LT, 0)])
notes(s, "REHEARSE THIS. It's the whole pitch.\n\n"
         "Start the probe in CHILLED water, not room air. At room temperature it reads "
         "about 73F, which is already 30 degrees above the produce ceiling — the dashboard "
         "would open in alarm and the demo loses its arc.\n\n"
         "Hot tap water is around 130F. Plenty dramatic, and safer for the probe than boiling.\n\n"
         "The third beat is the one people remember. Most monitoring shows a gap and leaves "
         "you guessing. This says which failure it was.")

# ══════════════════════════ 4 · ALERTING ══════════════════════════
s = slide(prs)
header(s, 3, "Alerting", "Three failures, not one")
rows = [
    ("Too warm, or too cold", COLD,
     "Each unit judged against its own limits. Produce at 36–43°F and a freezer at "
     "−9 to 0°F run on the same rule."),
    ("Sensor stops reporting", WARM,
     "A dead sensor sends nothing, so a temperature rule has nothing to fire on. "
     "This one watches for the silence."),
    ("Battery running down", GOOD,
     "Flagged before it goes dark, so it's replaced on schedule instead of discovered "
     "after a loss."),
]
y = Inches(2.42)
for head, col, body in rows:
    rect(s, M, y, Inches(0.05), Inches(0.95), col)
    tx(s, M + Inches(0.35), y + Inches(0.02), Inches(4.4), Inches(0.35),
       [(head, 17, True, INK, 0)])
    tx(s, M + Inches(0.35), y + Inches(0.4), Inches(4.3), Inches(0.55),
       [("", 1, False, INK, 0)])
    tx(s, M + Inches(5.1), y + Inches(0.06), Inches(6.4), Inches(0.85),
       [(body, 13, False, MUTED, 0)], ls=1.35)
    y += Inches(1.18)

rect(s, M, Inches(6.05), CW, Inches(0.92), PANEL, rounded=True)
tx(s, M + Inches(0.4), Inches(6.22), CW - Inches(0.8), Inches(0.6),
   [("Worth asking SmartSense: ", 14, True, INK, 0),
    ("if a sensor dies at 2am, what tells you — and how long before you know?",
     14, False, MUTED, 0)])
foot(s, "Alerts group by company and site, so each manager only gets their own.")
notes(s, "The middle row is the differentiator. Spend your time there.\n\n"
         "I don't know what SmartSense does or doesn't catch, so don't claim it. "
         "Ask the question instead — it's more disarming and it can't backfire. "
         "If they can answer it well, fine; you've still shown you thought about the "
         "failure mode that actually loses product.\n\n"
         "A silent sensor is worse than a warm one. A warm one you can see.")

# ══════════════════════════ 5 · COST ══════════════════════════
s = slide(prs, DARK)
header(s, 4, "Cost", "Five years, four sites", dark=True)

BAR_X, BAR_W = M, Inches(8.4)
SS_TOTAL, MY_TOTAL = 31400, 2470

tx(s, BAR_X, Inches(2.45), Inches(4), Inches(0.3),
   [("SMARTSENSE", 11.5, True, WARM_LT, 0)])
rect(s, BAR_X, Inches(2.8), BAR_W, Inches(0.72), WARM)
tx(s, BAR_X + BAR_W + Inches(0.3), Inches(2.85), Inches(2.6), Inches(0.6),
   [("$31,400", 30, False, PAPER, 0, DISPLAY)])
tx(s, BAR_X, Inches(3.62), Inches(8), Inches(0.3),
   [("$7,400 hardware   +   $24,000 in subscriptions", 12, False, RGBColor(0x8E, 0xA2, 0xAB), 0)])

tx(s, BAR_X, Inches(4.35), Inches(4), Inches(0.3),
   [("MINE", 11.5, True, COLD_LT, 0)])
rect(s, BAR_X, Inches(4.7), Inches(BAR_W * MY_TOTAL / SS_TOTAL), Inches(0.72), COLD)
tx(s, BAR_X + Inches(0.95), Inches(4.75), Inches(2.6), Inches(0.6),
   [("$2,470", 30, False, PAPER, 0, DISPLAY)])
tx(s, BAR_X, Inches(5.52), Inches(8.4), Inches(0.3),
   [("$1,400 hardware   +   $350 calibration reference   +   $720 hosting",
     12, False, RGBColor(0x8E, 0xA2, 0xAB), 0)])

rect(s, M + Inches(9.9), Inches(2.45), Inches(0.015), Inches(3.4), HAIR_D)
side = [("$370", "their cost per point"), ("$70", "mine"),
        ("$100", "their monthly fee, per site"), ("$12", "mine, all sites")]
y = Inches(2.45)
for big, lab in side:
    tx(s, M + Inches(10.25), y, Inches(2.2), Inches(0.42),
       [(big, 21, False, PAPER, 0, DISPLAY)])
    tx(s, M + Inches(10.25), y + Inches(0.38), Inches(2.2), Inches(0.42),
       [(lab, 10.5, False, RGBColor(0x8E, 0xA2, 0xAB), 0)], ls=1.2)
    y += Inches(0.87)

tx(s, M, Inches(6.35), CW, Inches(0.5),
   [("About $29,000 back over five years — and the gap widens with every site we add.",
     19, False, PAPER, 0, DISPLAY)])
foot(s, "Modelled on four sites at five monitoring points each. Replace with our real counts.", dark=True)
notes(s, "REPLACE THESE NUMBERS with Plymouth's real site count before you present. "
         "The maths only gets better — their cost is per-site, mine isn't.\n\n"
         "Say the big number once, then stop talking. Let it sit.\n\n"
         "If pushed on the $12 hosting: it's a small cloud server running the whole stack. "
         "Storage is nothing — twenty sensors generate about 350MB a year.\n\n"
         "The $350 calibration reference is a single NIST-traceable thermometer that "
         "calibrates the entire fleet. That's the answer to 'but theirs come pre-calibrated'.")

# ══════════════════════════ 6 · INSTALLATION ══════════════════════════
s = slide(prs)
header(s, 5, "Installation", "Wall power, and a probe through the door seal")
left = [
    ("Mains powered", "Freezers and server rooms both have power. No batteries to manage, "
                      "and no dead sensor because nobody swapped a cell."),
    ("Probe through the gasket", "A flat cable passes through the door seal without "
                                 "compromising it. Nothing gets drilled, nothing gets modified."),
    ("Enclosure I print myself", "About $10, and I can change the shape for whatever "
                                 "mounting a site needs."),
]
y = Inches(2.4)
for head, body in left:
    tx(s, M, y, Inches(6.0), Inches(0.32), [(head, 16, True, INK, 0)])
    tx(s, M, y + Inches(0.36), Inches(5.9), Inches(0.75),
       [(body, 12.5, False, MUTED, 0)], ls=1.35)
    y += Inches(1.32)

rect(s, M + Inches(6.55), Inches(2.35), Inches(4.95), Inches(3.55), PANEL, rounded=True)
tx(s, M + Inches(6.95), Inches(2.62), Inches(4.2), Inches(0.35),
   [("WHY NOT BATTERIES", 11.5, True, WARM, 0)])
tx(s, M + Inches(6.95), Inches(3.08), Inches(4.2), Inches(2.6),
   [("Lithium cells lose 20–40% of their capacity at freezer temperatures.", 13.5, False, INK, 0),
    ("Every one of these installs is somewhere with a wall socket a few feet away. "
     "Running on mains removes an entire category of failure — and it's why I can "
     "report every few minutes instead of once an hour.", 12.5, False, MUTED, 10)], ls=1.35)
foot(s, "Same hardware for warehouse freezers and server rooms — only the temperature limits differ.")
notes(s, "Facilities teams worry you're going to drill into a freezer wall. Say early "
         "that nothing gets drilled — flat gasket cables are standard practice.\n\n"
         "The battery box pre-empts the obvious question. Mains isn't a compromise here, "
         "it's the right answer: everything we're monitoring is a fixed installation with "
         "power already at it.")

# ══════════════════════════ 7 · OPEN ITEMS ══════════════════════════
s = slide(prs)
header(s, 6, "Open items", "What I still have to solve")
items = [
    ("The probe isn't accurate enough for frozen",
     "The current sensor is rated ±0.9°F only above 14°F. For freezers I move to an RTD "
     "probe — ±0.27°F across the whole range, $8–15 a unit. Chilled produce is fine as-is."),
    ("Calibration has to be auditable",
     "One NIST-traceable reference thermometer, roughly $350, calibrates the whole fleet "
     "with documentation an auditor will accept. Their $125 per sensor buys the same thing, "
     "over and over."),
    ("Security needs hardening before it carries real data",
     "The prototype runs on a trusted network. Production adds encrypted transport and "
     "per-device credentials. Known work, not a surprise."),
]
y = Inches(2.42)
for head, body in items:
    tx(s, M, y, Inches(11.4), Inches(0.32), [(head, 16, True, INK, 0)])
    tx(s, M, y + Inches(0.38), Inches(11.2), Inches(0.62),
       [(body, 12.5, False, MUTED, 0)], ls=1.35)
    rect(s, M, y + Inches(1.14), CW, Inches(0.015), HAIR)
    y += Inches(1.42)
tx(s, M, Inches(6.75), CW, Inches(0.4),
   [("I'd rather raise these than have you find them. None of them change the numbers.",
     14, True, COLD, 0)])
notes(s, "This slide is why they'll believe the rest of the deck.\n\n"
         "A pitch with no acknowledged weaknesses reads as a demo. Naming the sensor "
         "accuracy problem yourself — before anyone who knows sensors asks — is the single "
         "most credible thing in the presentation.\n\n"
         "The calibration line is also your rebuttal on price. Say it out loud: their $125 "
         "per sensor buys traceability. I buy it once, for $350, for the whole fleet.")

# ══════════════════════════ 8 · THE ASK ══════════════════════════
s = slide(prs, DARK)
header(s, 7, "Next", "Let me run one site for 30 days", dark=True)
steps = [
    ("Install alongside what's already there", "Both systems running on the same freezers. "
                                               "Nothing gets turned off."),
    ("Compare the data at the end of the month", "Same equipment, same conditions. "
                                                 "If mine doesn't hold up, we've lost a few hundred dollars."),
    ("Move sites across one at a time", "Each subscription cancels only after its "
                                        "replacement has proven itself."),
]
y = Inches(2.6)
for i, (head, body) in enumerate(steps, 1):
    tx(s, M, y, Inches(0.5), Inches(0.5), [(f"{i}", 22, False, COLD_LT, 0, DISPLAY)])
    tx(s, M + Inches(0.65), y + Inches(0.03), Inches(5.3), Inches(0.5),
       [(head, 16, True, PAPER, 0)], ls=1.25)
    tx(s, M + Inches(6.3), y + Inches(0.05), Inches(5.2), Inches(0.75),
       [(body, 13, False, RGBColor(0x9E, 0xB2, 0xBA), 0)], ls=1.35)
    y += Inches(1.18)
rect(s, M, Inches(6.15), CW, Inches(0.015), HAIR_D)
tx(s, M, Inches(6.45), CW, Inches(0.5),
   [("One site, one month, a few hundred dollars of hardware.", 19, False, PAPER, 0, DISPLAY)])
notes(s, "Ask for the pilot, not the contract. It's a small yes.\n\n"
         "The strongest thing about running in parallel is that it costs them nothing to "
         "be wrong about you. If the data doesn't hold up, they've spent a few hundred "
         "dollars and learned something.\n\n"
         "Then stop talking and let them respond.")

out = r"C:\Users\julia.lavigne\fleet-telemetry-pipeline\presentation\Fleet-Temperature-Monitoring.pptx"
prs.save(out)
print(f"saved: {out}")
