# Exercise video config

Hand-edited input for `jobs/exercise_videos.py`, which builds and re-checks
[exercise-videos.md](exercise-videos.md) (generated — don't edit that one).

Rules the job follows: search `<exercise name> form tutorial`; take the top result that is
1–8 minutes long, from a channel in the allowlist below, whose title contains the exercise
name or a synonym from the table below; store it only after the link is fetched
successfully. No qualifying result → no video, and the exercise goes on the "needs manual
pick" list. The search is never widened beyond this allowlist.

## Channel allowlist

`Channel ID` is filled in by `python jobs/exercise_videos.py --resolve-channels`, which
looks the channel up by name and asks you to confirm before it's used. Only rows with a
Channel ID and status `approved` are searched.

| Group | Channel | Channel ID | Status |
|---|---|---|---|
| Hospitals & health services | Sunnybrook Hospital | | pending |
| Hospitals & health services | NHS | | pending |
| Hospitals & health services | Health e-University | | pending |
| Physical therapists | Hinge Health | | pending |
| Physical therapists | Bob & Brad | | pending |
| Physical therapists | Ask Doctor Jo | | pending |
| Physical therapists | E3 Rehab | | pending |
| Postpartum / pelvic-floor physios | *(proposed by `--suggest-channels "postpartum pelvic floor exercises physiotherapist"`, added after your OK)* | | |
| Calisthenics coaches | Calisthenicmovement | | pending |

## Synonyms

Extra names a video title may use for an exercise (comma-separated). The library name
before any "(" or "—" is always accepted.

| Exercise id | Also called |
|---|---|
| `br-360` | diaphragmatic breathing, belly breathing, 360 breathing |
| `br-ta` | transverse abdominis, TA activation, core activation, pelvic floor breathing |
| `br-wind` | box breathing, relaxation breathing, 4-7-8 breathing |
| `ex-deadbug-heel` | dead bug heel tap, heel taps |
| `ex-sit-stand` | sit to stand, chair stand, sit-to-stand |
| `ex-chair-squat` | box squat, squat to chair |
| `ex-squat` | air squat, bodyweight squat |
| `ex-bridge` | glute bridge, hip bridge |
| `ex-bridge-march` | marching bridge, glute bridge march |
| `ex-bridge-1leg` | single leg glute bridge, one leg bridge |
| `ex-lunge-assist` | assisted reverse lunge, supported lunge |
| `ex-split-squat-sofa` | bulgarian split squat, rear foot elevated split squat |
| `ex-pushup-wall` | wall push up, wall pushup, wall press up |
| `ex-pushup-counter` | incline push up, counter push up |
| `ex-pushup-sofa` | incline push up |
| `ex-pushup-knee` | knee push up, kneeling push up |
| `ex-prone-ytw` | ytw, y t w raises, prone y raise |
| `ex-plank-incline` | incline plank, elevated plank |
| `ex-plank-knee` | kneeling plank, knee plank, modified plank |
| `ex-plank-taps` | shoulder taps, plank shoulder tap |
| `ex-side-plank-knee` | kneeling side plank, modified side plank |
| `cd-step-jack` | step jacks, low impact jumping jack |
| `cd-stairs` | stair climbing, stair workout |
| `cd-circuit-low` | low impact cardio, low impact workout |
| `mb-open-book` | open book stretch, thoracic rotation |
| `mb-hip-flexor` | kneeling hip flexor stretch, half kneeling hip flexor |
| `mb-doorway` | doorway pec stretch, doorway chest stretch |
| `mb-child` | child's pose, childs pose |
| `mb-desk-reset` | desk stretches, office stretches |

## Manual picks

When an exercise is on the "needs manual pick" list, paste a video link you chose here.
The job checks it (link works, 1–8 minutes, channel noted) before adopting it; an allowlist
channel is not required for your own picks.

| Exercise id | Video URL |
|---|---|
