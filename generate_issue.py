#!/usr/bin/env python3
"""
THE WEEKLY WOOLONG — weekly generation pipeline (TEXT ONLY)
===========================================================
Generates one weekly issue of writing. NO image generation — images on the
site are human-submitted (the placeholders + the Artistic Bounties program).
This keeps cost to fractions of a cent per issue (text tokens only).

Two passes:
  1. SHOWRUNNER  -> advances the world one week (events + updated state)
  2. WRITERS     -> turns events into article copy
Then plain file I/O writes the new state, latest.json, and rolls the archive.

The AI only ever RETURNS TEXT (JSON). This script does every file change.
Safety net: invalid JSON or an allow-list trip -> ABORT, change nothing live.

------------------------------------------------------------------
SETUP (one time):  py -m pip install openai   and set OPENAI_API_KEY
RUN:               py generate_issue.py
------------------------------------------------------------------
"""

import re
import json
import datetime
from pathlib import Path

from openai import OpenAI

# ---------------- CONFIG ----------------
ROOT         = Path(__file__).parent
STATE_FILE   = ROOT / "weekly-woolong-state.json"
OUT_LATEST   = ROOT / "latest.json"
ARCHIVE_DIR  = ROOT / "archive"
ARCHIVE_KEEP = 3
TEXT_MODEL   = "gpt-4o"   # any current capable chat model; update if name changes

client = OpenAI()  # reads OPENAI_API_KEY from the environment

# ---------------- PROMPTS ----------------
SHOWRUNNER_SYSTEM = """You are the Showrunner of The Weekly Woolong, a Cowboy Bebop news paper set in 2026, four years after the Astral Gate accident. You do not write articles. You advance a fictional solar system one week and decide what happened.

Routine, exactly:
1. Advance the clock one in-world week; update meta (issue +1, in_world_week +1).
2. EVERY section gets fresh news each issue — none may repeat or go stale. Produce at least one event for each of: astro, earth, econ, gate, bounty, irsi, citizen, biz. Drive these from the threads where possible: push 2-3 'developing' threads forward by one of their next_beats, optionally resolve 1 that has run its course, optionally seed 1 new thread only if fewer than 4 are active, let 1 'background' thread simmer. Sections not touched by a thread this week still get a smaller standalone beat so they're never empty.

VARIETY MANDATE — do not get stuck on the same subjects. ROTATE locations every issue across the whole system: Mars, Venus, Earth, the Moon debris belt, Ganymede, Callisto, Io, Europa, Titan, the Asteroid Belt (Tijuana, Linus Mine, Bohemian Junkheap), Pluto, Uranus. Do NOT make every issue Mars-vs-Ganymede. ROTATE businesses across the roster, not just the same three. The CITIZEN STORY must feature a brand-new random person and a different walk of life every single issue (miner, freighter pilot, dome farmer, Belt salvager, terraform tech, medic, elder, kid, athlete, artist) — NEVER reuse HexaChess or a prior winner; invent a new name and situation each week. Base everything on the Lore and the live state, not on echoing earlier issues. If a thread has been the headline two issues running, move it to 'background' and surface a different region or topic.
3. Apply the ripple model: every event nudges connected variables. Gate stability -> freight -> economy -> bounties -> citizens. Syndicate activity -> currency + unrest + crime. Meteor severity -> Earth + migration + economy. Business launches -> stocks + jobs + prestige. Faction tension -> gate routes + treaties.
4. Update every rendered number so it reflects the week's events: stock prices/trends, bounty statuses, faction postures, location statuses, and a fresh irsi_forecast (4 impacts with sector, lat, lon, eta_minutes, severity). DO NOT touch woolong_per — it is manually managed and locked.
WOOLONG EXCHANGE RATE — HARD ANCHOR. The woolong is anchored at 100 woolongs = 1 USD (so 1 woolong = US$0.01). It is the most STABLE currency in the system — a reliable store of value. Therefore woolong_per may only drift within a TIGHT band (about ±2%, never more than ±3%) from these canonical anchors, and never trend away over time — it always returns toward the peg:
  USD: 100 (anchor, 100₩ = $1) | EUR: 108 | GBP: 127 | JPY: 0.65
Only a major, explicitly-written economic shock (a thread you are actively running) may move it more, and even then it recovers within an issue or two. Do NOT let it wander. The STOCKS (GINA/HEXA/PIPP) are the volatile thing — let those swing; keep the currency steady.
5. Advance characters states. Write any durable invention (company, colony, person) into its roster so it persists.

Hard rules: status integrity (a 'captured' bounty or 'resolved' thread never reverts). Timeline guards (NO Titan war, gates only partially rebuilt, syndicates still forming, main cast absent). Allow-list (crimes are heists / syndicate rackets-and-riots / dealing only — never murder, sexual content, mass-casualty terror, or anything lingering on victims). Keep ~3-4 developing threads; stagger seeds and payoffs.

WHAT YOU REGENERATE vs WHAT YOU NEVER TOUCH:
- REGENERATE EVERY ISSUE: all eight news desks (astro, earth, econ, gate, bounty, irsi, citizen, biz), the DJ/broadcast patter, stocks, and irsi_forecast. Every article is fresh every week — nothing carries over verbatim, nothing goes stale.
- NEVER TOUCH (these are human-kept and static): the Foodbook page (recipes, grow guides), the About / "AI & the environment" page, the Archive mechanism, and the WOOLONG SYSTEM (rates/converter). Do not write, reference-as-news, or regenerate any of these. They live outside the weekly loop permanently.

Output JSON ONLY, no prose, no markdown fences:
{"events":[{"section":"...","summary":"...","thread_id":"...","ripples":["..."]}],
 "updated_state":{ ...the FULL state object, advanced, same shape as input... },
 "ledger_entry":["short bullets of what happened"]}"""

WRITERS_SYSTEM = """You are the staff of The Weekly Woolong. You will be given this week's events. Write the issue in the paper's voice and return JSON the website reads.

Voice: clean, literate, objective newswire English — the register of a real wire service (think Reuters/AP) reporting an extraordinary world plainly. Measured and readable. NO slang, NO internet-speak, NO DJ patter, NO forced quirk. The interest comes from the events and from specific concrete detail ("a roof patched four times" over "damaged infrastructure"), not from narrator personality. Sentences can be full and varied; this is not terse minimalism — it's proper reporting.

OBJECTIVITY — HARD RULE (all NEWS DESKS: astro, earth, econ, gate, bounty, citizen, biz, and straight IRSI forecast reporting). Report only what can be observed or attributed. FORBIDDEN: mind-reading ("the syndicates noticed"), advice to the reader, prediction ("by next week it might…"), and editorial asides ("nobody noticed", "they always say alive"). Every non-obvious claim gets a source: "ISSP said", "the governor's office stated", "traders reported", "according to the filing". If it can't be attributed, cut it.

CLEAN LANGUAGE — no profanity, no graphic content, no slurs. Keep it broadcast-clean so no censoring is needed. The allow-list still holds: crimes are heists / syndicate rackets-and-riots / dealing only — never murder, sexual content, mass-casualty terror, or anything lingering on victims.

EXCEPTIONS (first-person columns, allowed to be subjective and warmer): IRSI's personal sign-off line and the three old men's op-ed. They may address the reader. IRSI's forecast data and reporting stays objective; only its sign-off is free.

QUOTES — REQUIRED. Every lead must include at least one direct quote from a named (invented) source — an official, party spokesperson, governor, ISSP officer, business figure, union rep, scientist, or witness. Quotes sound like real people: measured, hedged, political where fitting ("We have to weigh the colony's needs against the gate's risks before we commit to anything," the governor said). Invent a plausible name and title. Two quotes from opposing sides is ideal for political/economic desks. This is the biggest single thing that makes it read real.

FRESHNESS & VARIETY — CRITICAL. Do NOT keep returning to the same subjects. Across the system there are MANY places: Mars, Venus, Earth, the Moon debris belt, Ganymede, Callisto, Io, Europa, Titan, the Asteroid Belt (Tijuana, Linus Mine, the Bohemian Junkheap), Pluto, Uranus — ROTATE through them; do not let every story be Mars-vs-Ganymede. Many businesses exist (GATE, ISSP, Cherious Medical, WcDonald's, Big Shot, Gina Motors, HexaChess, Pippu Cola, Helios Solar Freight, Lumen Relay Co., Ganymede Blue, Tharsis Dome Works, Red Sand Refineries, Venus Bloom, Io Green Growers, First Solar Bank) — feature different ones. CITIZEN STORY especially must be a DIFFERENT random person and a DIFFERENT kind of story every issue — a miner, a freighter pilot, a dome farmer, a Belt salvager, a Venus terraform tech, a kid, an elder, a medic, an athlete, an artist — NOT HexaChess again, NOT the same winner. Invent new names every week. Treat the provided events and Lore as your source of truth; do NOT echo or paraphrase any previous issue's wording or subjects.

Per-desk angle (clean voice throughout): astro = system geopolitics, factions, treaties, gate routes — rotate which powers. earth = elegiac, the wounded home planet. econ = markets, the woolong, business — numbers and attribution. gate = transit, safety reviews, bureaucratic dread. bounty = wanted-poster terse, menace from reputation not gore, the "alive" line. irsi = objective forecast + one short first-person sign-off. citizen = a fresh ordinary person each week (see above). biz = frontier industry and innovation, rotate companies. oldmen = rambling, contradictory, comic op-ed; never remember each other.

Length: lead 200-320 words (longer than before — give it room for quotes and detail); short item 90-150; bounty poster 1-2 sentences; oldmen column 110-180. Headlines specific and grounded, not gimmicky. Hard-news byline "— Woolong Wire / [Desk]".

IMAGES ARE NOT GENERATED — they are commissioned from human artists. For each article, write an "image_brief": one or two sentences describing the ideal photo or artwork a contributor could submit for that story (subject, mood, framing). Write it as a real call for art, in the paper's voice where it fits. Example: "WANTED: a wide shot of a half-built Mars dome at dusk, one warm light on inside, everything else cold. Bonus for grain." This brief is shown in the placeholder and becomes the public submission ask.

Output JSON ONLY, no prose, no markdown fences:
{"issue_meta":{"volume":N,"issue":N,"edition_label":"..."},
 "articles":[{"section":"astro|earth|econ|gate|bounty|irsi|citizen|biz","headline":"...","byline":"...","body":"...","image_brief":"..."}],
 "bounties":[{"name":"...","line":"...","reward":N,"status":"open"}],
 "oldmen_column":{"headline":"...","body":"..."},
 "stocks":[{"ticker":"GINA","price":N,"trend":"up|down"},{"ticker":"HEXA","price":N,"trend":"up|down"},{"ticker":"PIPP","price":N,"trend":"up|down"}],
 "irsi_forecast":[{"sector":"...","lat":N,"lon":N,"eta_minutes":N,"severity":"..."}]}"""

# ---------------- HELPERS ----------------
def call_model(system_prompt, user_content, force_json=True):
    kwargs = dict(
        model=TEXT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.9,
    )
    # Ask the API to guarantee valid JSON when the model supports it. This alone
    # prevents most "missing comma" failures. Harmless to try; ignored if unsupported.
    if force_json:
        try:
            kwargs["response_format"] = {"type": "json_object"}
        except Exception:
            pass
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content

def _salvage_json(text):
    """Best-effort cleanup for minor model slips before parsing."""
    s = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    # trim anything before the first { or after the last } (stray prose)
    if "{" in s and "}" in s:
        s = s[s.index("{"): s.rindex("}") + 1]
    # remove trailing commas before } or ] (a very common model slip)
    s = re.sub(r",(\s*[}\]])", r"\1", s)
    return s

def parse_json(text, label):
    try:
        return json.loads(_salvage_json(text))
    except json.JSONDecodeError as e:
        raise ValueError(f"[{label}] did not return valid JSON: {e}\n--- raw ---\n{text[:600]}")

def get_json(system_prompt, user_content, label, retries=2):
    """Call the model and parse JSON, retrying a few times on malformed output.
    This turns a one-off bad-comma run from a hard abort into a self-heal."""
    last_err = None
    for attempt in range(1, retries + 2):
        raw = call_model(system_prompt, user_content)
        try:
            return parse_json(raw, label)
        except ValueError as e:
            last_err = e
            print(f"      (retry {attempt}: {label} JSON slipped, asking again...)")
    raise last_err  # all attempts failed -> the safety net aborts cleanly

def check_allow_list(writers):
    banned = ["massacre", "terrorist", "bomb the"]
    blob = json.dumps(writers).lower()
    hits = [w for w in banned if w in blob]
    if hits:
        raise ValueError(f"Allow-list tripwire hit: {hits}. Aborting without publishing.")

# ---------------- PIPELINE ----------------
def main():
    print("== The Weekly Woolong :: weekly run (text only) ==")
    state = json.loads(STATE_FILE.read_text())
    recent_ledger = state.get("ledger", {})
    print(f"  loaded state: Vol.{state['meta']['volume']} No.{state['meta']['issue']}")

    # PASS 1 — Showrunner
    print("  [1/3] Showrunner: advancing the world one week...")
    sr_user = (
        "CURRENT STATE:\n" + json.dumps(state, ensure_ascii=False)
        + "\n\nLAST LEDGERS:\n" + json.dumps(recent_ledger, ensure_ascii=False)
        + "\n\nAdvance one in-world week. Return JSON only."
    )
    showrunner   = get_json(SHOWRUNNER_SYSTEM, sr_user, "Showrunner")
    # required keys — fail clearly if these are missing
    if "updated_state" not in showrunner:
        raise ValueError("Showrunner JSON missing 'updated_state' (the advanced world).")
    events       = showrunner.get("events", [])
    new_state    = showrunner["updated_state"]
    # ledger_entry is cosmetic; if the model forgot it, derive one from events
    # rather than aborting the whole run over a missing summary field.
    ledger_entry = showrunner.get("ledger_entry")
    if not ledger_entry:
        ledger_entry = [e.get("summary", "") for e in events if e.get("summary")] or ["(issue published; no summary returned)"]
    if "meta" not in new_state or "issue" not in new_state.get("meta", {}):
        raise ValueError("Showrunner's updated_state is missing meta.issue — check the returned JSON shape.")
    issue_no     = new_state["meta"]["issue"]
    print(f"      -> {len(events)} events; issue is now No.{issue_no}")

    # PASS 2 — Writers
    print("  [2/3] Writers: writing the issue...")
    wr_user = (
        "THIS WEEK'S EVENTS:\n" + json.dumps(events, ensure_ascii=False)
        + f"\n\nWrite Vol.{new_state['meta']['volume']} No.{issue_no}. Return JSON only."
    )
    writers = get_json(WRITERS_SYSTEM, wr_user, "Writers")
    check_allow_list(writers)
    print(f"      -> {len(writers.get('articles', []))} articles; allow-list OK")

    # PASS 3 — Write + roll (plain file I/O, no AI)
    print("  [3/3] Writing files and rolling the archive...")
    today = datetime.date.today().isoformat()
    new_state["meta"]["real_publish_date"] = today
    new_state.setdefault("ledger", {})[f"issue_{issue_no}"] = ledger_entry
    _trim_ledger(new_state["ledger"], issue_no)

    STATE_FILE.write_text(json.dumps(new_state, ensure_ascii=False, indent=2))   # save memory
    OUT_LATEST.write_text(json.dumps(writers, ensure_ascii=False, indent=2))     # site reads this
    ARCHIVE_DIR.mkdir(exist_ok=True)
    (ARCHIVE_DIR / f"issue_{issue_no}.json").write_text(json.dumps(writers, ensure_ascii=False, indent=2))
    _roll_archive(issue_no)

    print(f"== Done. Vol.{new_state['meta']['volume']} No.{issue_no} staged. ==")
    print("   Review latest.json, then commit & push to publish.")

def _trim_ledger(ledger, current_issue):
    keep = {f"issue_{n}" for n in range(current_issue, current_issue - ARCHIVE_KEEP, -1)}
    for k in list(ledger.keys()):
        if k not in keep:
            del ledger[k]

def _roll_archive(current_issue):
    cutoff = current_issue - ARCHIVE_KEEP
    for f in ARCHIVE_DIR.glob("issue_*.json"):
        n = int(re.findall(r"issue_(\d+)", f.name)[0])
        if n <= cutoff:
            f.unlink()
            print(f"      rolled out issue {n} (past 3-week window)")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\nXX RUN ABORTED — site NOT changed.")
        print(f"   Reason: {e}")
        print("   This is the fall-back-to-last-week safety net working as designed.")
        raise SystemExit(1)