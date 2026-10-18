# Exercise library

Every exercise in any plan comes from this list, referenced by its **id**. To add an
exercise, add a row here first — plans never use an exercise that is not in this file.
(This is the same rule the future bot will follow: decisions 054 and 075.)

**Equipment: none.** A mat or rug, a wall, a sturdy chair, the sofa, the kitchen counter
and the building's stairs. Nothing to buy.

**Levels:** 0 = foundations (safe for everyone, including postpartum) · 1 = easy ·
2 = moderate · 3 = solid. Everyone starts at level 0–1 and moves up by the rules in
[progression.md](progression.md).

**Flags** used in the tables:
- **PP** — postpartum caution: Karine only after the symptom self-check is clear
  (see [progression.md](progression.md#postpartum-gate)).
- **IMPACT** — jumping / landing. Locked for Karine until cleared; optional for Davit
  from week 9.
- **MEAL** — compresses the stomach or puts the head below the heart: not within
  ~2 hours of a main meal (gastritis).
- **KID** — the son can "join" by copying, as play.

---

## Breathing and core foundations

| id | name | level | how (key cues) | easier → harder | flags |
|---|---|---|---|---|---|
| `br-360` | 360° breathing | 0 | Lie on back, knees bent. Breathe in through the nose so belly, sides and lower back all expand; long slow exhale. 5–10 breaths. | — → `br-ta` | — |
| `br-ta` | Deep-core activation | 0 | Same position. On the exhale, gently draw the lower belly in (as if zipping tight jeans) and lift the pelvic floor; release fully on the inhale. 8–10 reps. | `br-360` → `ex-deadbug-heel` | — |
| `br-wind` | Wind-down breathing | 0 | Seated or lying. Inhale 4 s, exhale 6–8 s. 3–5 min before sleep. | — | — |
| `ex-deadbug-heel` | Dead bug — heel taps | 0 | On back, knees at 90° in the air. Slowly lower one heel to tap the floor, return, switch. Lower back stays heavy on the floor. 6–8 per side. | `br-ta` → `ex-deadbug` | MEAL |
| `ex-deadbug` | Dead bug — opposite arm and leg | 2 | As above, extend the opposite arm overhead and leg long together. 6–8 per side. | `ex-deadbug-heel` → — | MEAL, PP |
| `ex-birddog` | Bird-dog | 0 | On hands and knees. Reach one arm forward and the opposite leg back, hold 2 s, return. Hips stay level. 6–8 per side. | — → `ex-birddog-hold` | KID |
| `ex-birddog-hold` | Bird-dog with 5 s holds | 1 | Same, hold 5 s each rep. | `ex-birddog` → `ex-plank-knee` | — |

## Lower body

| id | name | level | how (key cues) | easier → harder | flags |
|---|---|---|---|---|---|
| `ex-sit-stand` | Sit-to-stand (chair) | 0 | Sit on a chair edge, feet hip-width. Stand up without using hands, sit down slowly (3 s). 8–12 reps. | — → `ex-chair-squat` | KID |
| `ex-chair-squat` | Chair squat (touch and go) | 1 | Sit back until you just touch the chair, then stand. Knees track over toes, chest proud. 10–15 reps. | `ex-sit-stand` → `ex-squat` | KID |
| `ex-squat` | Bodyweight squat | 2 | No chair. Hips back and down as low as comfortable, heels down. 10–15 reps. | `ex-chair-squat` → `ex-squat-tempo` | KID |
| `ex-squat-tempo` | Tempo squat 3-1-1 | 3 | 3 s down, 1 s pause at the bottom, 1 s up. 8–12 reps. | `ex-squat` → — | — |
| `ex-bridge` | Glute bridge | 0 | On back, knees bent. Exhale and squeeze glutes to lift hips to a straight line knees-hips-shoulders, lower slowly. 10–15 reps. | — → `ex-bridge-march` | — |
| `ex-bridge-march` | Bridge march | 2 | Hold the bridge and lift one foot a few cm, alternate. Hips stay level. 6–8 per side. | `ex-bridge` → `ex-bridge-1leg` | PP |
| `ex-bridge-1leg` | Single-leg bridge | 3 | One foot on the floor, the other leg straight. 8–10 per side. | `ex-bridge-march` → `ex-hip-thrust` | PP |
| `ex-hip-thrust` | Hip thrust (shoulders on sofa) | 3 | Upper back on the sofa edge, drive hips up, squeeze 1 s. 10–15 reps. | `ex-bridge` → — | PP |
| `ex-lunge-assist` | Reverse lunge, holding the wall | 1 | Hand on wall. Step one foot back and lower the back knee towards the floor, return. 6–8 per side. | — → `ex-lunge` | — |
| `ex-lunge` | Reverse lunge | 2 | Same, no support. 8–10 per side. | `ex-lunge-assist` → `ex-split-squat-sofa` | PP |
| `ex-split-squat-sofa` | Rear-foot-elevated split squat | 3 | Back foot on the sofa, front foot far enough forward; lower straight down. 6–10 per side. | `ex-lunge` → — | PP |
| `ex-calf` | Calf raises (hold the wall) | 0 | Rise onto the balls of the feet, 1 s top, lower slowly. 12–20 reps. | — | KID |

## Upper body

| id | name | level | how (key cues) | easier → harder | flags |
|---|---|---|---|---|---|
| `ex-pushup-wall` | Wall push-up | 0 | Hands on the wall at chest height, body straight, lower chest to the wall, push back. 8–15 reps. | — → `ex-pushup-counter` | KID |
| `ex-pushup-counter` | Incline push-up (kitchen counter) | 1 | Hands on the counter edge. 8–12 reps. | `ex-pushup-wall` → `ex-pushup-sofa` | — |
| `ex-pushup-sofa` | Incline push-up (sofa / low chair) | 2 | Lower hand height = harder. 8–12 reps. | `ex-pushup-counter` → `ex-pushup-knee` | PP |
| `ex-pushup-knee` | Knee push-up | 2 | On the floor, from the knees, body straight knees-to-head. 6–12 reps. | `ex-pushup-sofa` → `ex-pushup` | PP |
| `ex-pushup` | Push-up | 3 | Full plank position. 5–12 reps. | `ex-pushup-knee` → — | PP |
| `ex-prone-ytw` | Prone Y-T-W raises | 1 | Lie face down, forehead on a towel. Lift arms into Y, then T, then W shapes, 3 s each, thumbs up. 2–3 rounds. Great antidote to desk posture. | — | MEAL |
| `ex-superman` | Superman hold | 2 | Face down, lift arms and legs slightly, hold 3–5 s. 6–10 reps. | `ex-prone-ytw` → — | MEAL, PP |

## Planks and anti-rotation

| id | name | level | how (key cues) | easier → harder | flags |
|---|---|---|---|---|---|
| `ex-plank-incline` | Incline plank (hands on sofa) | 1 | Straight line head to heels, breathe normally. 15–30 s. | — → `ex-plank-knee` | — |
| `ex-plank-knee` | Plank from knees | 1 | Forearms and knees on the floor, straight line knees-to-head. 15–30 s. | `ex-plank-incline` → `ex-plank` | MEAL, PP |
| `ex-plank` | Forearm plank | 2 | 20–45 s. Stop if the belly domes or the lower back sags. | `ex-plank-knee` → `ex-plank-taps` | MEAL, PP |
| `ex-plank-taps` | Plank shoulder taps | 3 | High plank, tap opposite shoulder, hips still. 8–12 per side. | `ex-plank` → — | MEAL, PP |
| `ex-side-plank-knee` | Side plank from knees | 1 | Elbow under shoulder, knees bent, lift hips. 15–25 s per side. | — → `ex-side-plank` | PP |
| `ex-side-plank` | Side plank | 2 | Legs straight. 15–30 s per side. | `ex-side-plank-knee` → — | PP |

## Conditioning (cardio, low impact first)

| id | name | level | how (key cues) | easier → harder | flags |
|---|---|---|---|---|---|
| `cd-walk` | Walk | 0 | Outdoors, with the stroller, or in the corridor. Brisk = you can talk but not sing. | — → `cd-walk-brisk` | KID |
| `cd-walk-brisk` | Brisk walk | 1 | Pace where talking takes effort. | `cd-walk` → `cd-stairs` | — |
| `cd-march` | Marching in place | 0 | Knees up, arms swinging. 1–3 min blocks. | — → `cd-step-jack` | KID |
| `cd-step-jack` | Step jacks (no jump) | 1 | Step one foot out while raising arms, alternate. 30–60 s. | `cd-march` → `cd-circuit-low` | KID |
| `cd-stairs` | Stair climbing (building stairs) | 2 | Walk up 2–4 floors, walk down carefully. Repeat. Hold the rail. | `cd-walk-brisk` → `cd-stairs-int` | — |
| `cd-stairs-int` | Stair intervals | 3 | Brisk up, easy down, 6–10 repeats. | `cd-stairs` → — | — |
| `cd-circuit-low` | Low-impact circuit | 2 | 40 s on / 20 s off, rotating: step jacks, march with high knees, standing knee-to-elbow, squat-to-calf-raise. 3–4 rounds. | `cd-step-jack` → `cd-circuit-impact` | KID |
| `cd-circuit-impact` | Impact circuit | 3 | As above with jumping jacks and light jogging in place. | `cd-circuit-low` → — | IMPACT, PP |
| `cd-dance` | Dance with the family | 0 | 2–3 favourite songs. Counts as conditioning. | — | KID |

## Mobility (desk antidote, daily)

| id | name | level | how (key cues) | flags |
|---|---|---|---|---|
| `mb-chin-tuck` | Chin tucks | 0 | Sit tall, glide the chin straight back (double chin), hold 3 s. 8–10 reps. | — |
| `mb-neck-tilt` | Neck side tilt | 0 | Ear towards shoulder, gentle, 20 s each side. | — |
| `mb-shoulder-roll` | Shoulder rolls | 0 | 10 slow backwards circles. | KID |
| `mb-open-book` | Thoracic open book | 0 | Lie on side, knees bent, rotate top arm open to the floor behind you. 6–8 per side. | — |
| `mb-cat-cow` | Cat-cow | 0 | On hands and knees, slowly round and arch the spine with the breath. 8–10 reps. | KID |
| `mb-child` | Child's pose | 0 | Knees wide, sit back on heels, arms long. 30–60 s. | MEAL, KID |
| `mb-hip-flexor` | Half-kneeling hip flexor stretch | 0 | One knee down, tuck the pelvis, shift forward gently. 30 s per side. The key stretch for long sitting. | — |
| `mb-hamstring` | Hamstring stretch (heel on chair) | 0 | Straight leg, hinge forward from the hips. 30 s per side. | — |
| `mb-wrist` | Wrist and forearm stretch | 0 | Arm straight, palm up then down, gently pull fingers back. 20 s each. | — |
| `mb-doorway` | Doorway chest stretch | 0 | Forearm on the door frame, step through gently. 30 s per side. | — |
| `mb-desk-reset` | 60-second desk reset | 0 | Stand up, 5 sit-to-stands, 10 shoulder rolls, 1 chin tuck set, look out the window 20 s. | — |
