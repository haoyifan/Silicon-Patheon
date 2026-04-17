# Proposed Scenarios — Fiction & Fantasy Battles

20 scenario proposals from popular novels, anime, and films. Each is
designed to translate well to SiliconPantheon's grid-based tactical
combat with historically/narratively accurate unit compositions.

---

## Game of Thrones / A Song of Ice and Fire

### 1. Battle of the Bastards
**Blue:** Jon Snow's coalition (Stark loyalists)
**Red:** Ramsay Bolton's army

**Plot:** Jon charges to save Rickon; Ramsay's cavalry encircles. The
Bolton shield wall closes in until the Knights of the Vale arrive.

**Units:**
- Blue: Jon Snow (VIP, knight, high HP), Tormund (berserker), Wun Wun
  (giant — massive HP, slow, 2-tile attack), 8× Free Folk warriors
  (light infantry), 4× Stark infantry
- Red: Ramsay Bolton (VIP, archer, stays behind), 6× Bolton cavalry
  (fast, flanking), 8× Bolton pikemen (high DEF, shield wall), 4×
  Bolton archers

**Win conditions:**
- Blue: kill Ramsay OR survive to turn cap (reinforcements coming)
  → `protect_unit_survives(jon) + protect_unit(jon)`
- Red: kill Jon OR eliminate all enemies before reinforcements

**Special:** Plugin reinforcement at turn 10 — 6× Vale knights spawn
on blue's south edge (the "Knights of the Vale" moment). Red must
win fast.

**Map:** 14×10, open field with corpse piles (terrain: movement penalty,
defense bonus) forming the historical "crush" funnel.

---

### 2. Battle of Winterfell (The Long Night)
**Blue:** The Living (Stark/Targaryen alliance)
**Red:** Army of the Dead (Night King)

**Plot:** The dead assault Winterfell. The Dothraki charge vanishes
into darkness. Melisandre lights the trenches. Arya kills the Night
King.

**Units:**
- Blue: Jon Snow (knight), Daenerys (dragon rider — ranged 3-5,
  flying, magic fire), Arya Stark (assassin — low HP, high SPD,
  can_heal: false, 1-hit-kill ability on VIP?), Brienne (knight),
  Grey Worm (spearman), 6× Unsullied (infantry, high DEF),
  4× Dothraki (cavalry, fast), Melisandre (mage, can_heal, fire)
- Red: Night King (VIP, dragon rider, magic, ice), 3× White Walkers
  (elite, magic), 20× wights (weak individually but many — HP 8,
  ATK 4, swarm), 1× undead Viserion (dragon, ranged fire/ice)

**Win conditions:**
- Blue: kill Night King → instant win (all wights collapse)
  → `protect_unit(night_king, red)` reversed — blue wins on NK death
- Red: kill all blue units OR breach Winterfell gate (reach_tile)

**Special:** Wights are expendable (low individual value). Night King
at rear. Fog of war "line_of_sight" — the Long Night is dark.
Trench terrain at y=4 blocks wights until turn 5 (fire expires).

**Map:** 16×12, Winterfell at south, open field to north, trenches
across the middle.

---

### 3. Battle of Blackwater Bay
**Blue:** Stannis Baratheon's fleet/army (attacking)
**Red:** Lannister defense of King's Landing

**Plot:** Stannis assaults King's Landing by sea. Tyrion's wildfire
trap destroys the fleet. Tywin arrives with Tyrell reinforcements.

**Units:**
- Blue: Stannis (VIP, commander), Davos (naval), 8× Baratheon
  infantry, 4× Baratheon archers, 2× siege towers (slow, high HP)
- Red: Tyrion (commander, low combat), Sandor Clegane (The Hound,
  berserker), Bronn (ranger/archer), 6× Lannister guards, 4× City
  Watch (weak), 2× wildfire traps (terrain)

**Win conditions:**
- Blue: reach the Iron Throne (reach_tile at Red Keep) OR kill Tyrion
- Red: kill Stannis OR survive to turn 12 (Tywin arrives)
  → `protect_unit_survives` for red

**Special:** Wildfire terrain tiles on the bay — any unit entering
takes massive damage (plugin effect). Tywin reinforcements (plugin
spawn turn 12).

**Map:** 16×10, Blackwater Bay (water/impassable) left half, city
walls on right, beach landing zone in center.

---

### 4. Loot Train Attack (Field of Fire 2.0)
**Blue:** Daenerys Targaryen + Dothraki
**Red:** Jaime Lannister's army (Loot Train)

**Plot:** Daenerys attacks the Lannister supply train with Drogon
and the Dothraki horde.

**Units:**
- Blue: Daenerys + Drogon (dragon rider, ranged 2-4, flying,
  fire breath AOE?), 12× Dothraki screamers (cavalry, fast,
  high ATK, low DEF)
- Red: Jaime Lannister (VIP, knight), Bronn (archer, anti-dragon
  scorpion), Dickon Tarly (knight), 8× Lannister infantry,
  4× Lannister archers, 2× supply wagons (0 ATK, high HP,
  must protect)

**Win conditions:**
- Blue: destroy supply wagons (eliminate specific units) OR kill Jaime
- Red: kill Daenerys/Drogon (bring down the dragon) OR protect
  wagons until turn cap

**Map:** 12×10, open grassland with the Roseroad as a terrain feature,
supply wagons in a line along red's back row.

---

## Harry Potter

### 5. Battle of Hogwarts
**Blue:** Order of the Phoenix + Hogwarts defenders
**Red:** Voldemort's Death Eaters + creatures

**Plot:** The final battle. Voldemort's army assaults Hogwarts.
Harry must survive to face Voldemort.

**Units:**
- Blue: Harry Potter (VIP, mage, Expelliarmus specialist),
  Hermione (mage, high RES), Ron (mage), Neville (mage, sword
  of Gryffindor — anti-snake bonus), McGonagall (mage, high ATK),
  Kingsley (auror), 6× DA members (student mages), 4× Order
  members (adult mages, stronger)
- Red: Voldemort (VIP, mage, highest ATK), Bellatrix (mage, high
  ATK), Lucius Malfoy (mage), 6× Death Eaters (mages),
  4× Snatchers (weak infantry), Nagini (snake — must be killed
  for Voldemort to be killable, special plugin), 2× giants
  (massive HP, melee)

**Win conditions:**
- Blue: kill Nagini AND THEN kill Voldemort (plugin compound rule)
- Red: kill Harry Potter

**Special:** ALL units are mages (magic damage uses RES not DEF).
Nagini plugin: Voldemort is invulnerable until Nagini dies.
Hogwarts castle terrain provides high defense bonuses.

**Map:** 14×12, Hogwarts grounds. Castle walls at south (blue start),
open courtyard in center, forest at north (red approach).

---

### 6. Department of Mysteries
**Blue:** Dumbledore's Army (teenagers)
**Red:** Death Eaters

**Plot:** Harry leads 5 friends into the Department of Mysteries to
rescue Sirius. Outnumbered by Death Eaters until the Order arrives.

**Units:**
- Blue: Harry (mage), Hermione (mage), Ron (mage), Neville (mage,
  low stats but brave), Luna (mage, ranged), Ginny (mage)
- Red: Lucius Malfoy (mage), Bellatrix (mage), Dolohov (mage),
  4× Death Eaters (mages)

**Win conditions:**
- Blue: protect Harry + survive to turn 8 (Order arrives)
  → `protect_unit_survives`
- Red: seize the prophecy (reach_tile) OR kill Harry

**Special:** Tight indoor map. Order reinforcements (Sirius, Lupin,
Tonks, Moody) spawn at turn 8. Rooms connected by doorways
(chokepoints). All magic combat.

**Map:** 12×8, labyrinthine rooms with narrow corridors.

---

### 7. Battle of the Astronomy Tower
**Blue:** Dumbledore + Harry (then Order)
**Red:** Death Eaters (Draco's mission)

**Plot:** Draco disarms Dumbledore atop the tower. Death Eaters
invade Hogwarts. Snape kills Dumbledore.

**Units:**
- Blue: Dumbledore (powerful mage, but weakened — starts at half HP),
  Harry (invisible — can't act for first 3 turns, plugin), 4× Order
  members, 2× DA students
- Red: Draco Malfoy (mage, conflicted — low ATK), Snape (mage,
  double agent — switches sides at turn 5?), 4× Death Eaters,
  Fenrir Greyback (werewolf, melee, high ATK)

**Win conditions:**
- Blue: protect Dumbledore
- Red: kill Dumbledore

**Special:** Snape switch-sides plugin at turn 5 (betrayal narrative).
Tower terrain — verticality modeled as defense bonuses. Harry frozen
first 3 turns.

**Map:** 10×8, Hogwarts tower + corridors.

---

## Lord of the Rings (beyond existing scenarios)

### 8. Battle of the Pelennor Fields
**Blue:** Gondor + Rohan
**Red:** Mordor (Sauron's army)

**Plot:** The siege of Minas Tirith. Rohan rides to Gondor's aid.
The Witch-King confronts Éowyn.

**Units:**
- Blue: Gandalf (mage, high), Aragorn (ranger), Éowyn (shieldmaiden
  — bonus vs Witch-King), Théoden (VIP, cavalry), Legolas (archer,
  long range), Gimli (dwarf, high DEF), 6× Gondor soldiers,
  6× Rohirrim cavalry (reinforcement turn 6)
- Red: Witch-King (VIP, dragon rider, terror aura — adjacent
  enemies -2 ATK), Gothmog (orc commander), 10× orcs, 4× Haradrim
  (elephant-mounted — high HP, slow), 2× siege trolls (massive HP)

**Win conditions:**
- Blue: kill Witch-King + eliminate all enemies
- Red: breach Minas Tirith gate (reach_tile) OR kill Théoden

**Special:** Rohan cavalry arrives as reinforcement at turn 6 (the
horn of Helm Hammerhand). Witch-King has terror aura (adjacent
penalty). Pelennor is mostly open plain.

**Map:** 18×12, Minas Tirith walls at west, open Pelennor Fields,
river Anduin at east.

---

### 9. Amon Hen (Breaking of the Fellowship)
**Blue:** The Fellowship (fragmented)
**Red:** Uruk-hai (Saruman's elite)

**Plot:** Boromir's last stand protecting Merry and Pippin.

**Units:**
- Blue: Aragorn (ranger), Legolas (archer), Gimli (dwarf), Boromir
  (VIP — must die narratively but gameplay lets you try to save him),
  Frodo (hobbit, very weak, ring-bearer), Sam (hobbit), Merry
  (hobbit), Pippin (hobbit)
- Red: Lurtz (uruk captain, archer), 12× Uruk-hai (strong infantry)

**Win conditions:**
- Blue: protect Boromir OR get Frodo to the east bank (reach_tile)
- Red: capture hobbits (reach any hobbit's tile) OR kill Boromir

**Special:** Hobbits are very weak (HP 8, ATK 2) — blue must
protect them, not use them offensively. Forest terrain throughout.

**Map:** 12×10, dense forest, ruins of Amon Hen, river at east edge.

---

## The Matrix

### 10. Battle of Zion Dock
**Blue:** Zion defense forces (humans)
**Red:** Sentinels (machines)

**Plot:** The sentinels breach Zion's dock. APU (mech) pilots hold
the line. Niobe races to restart the power grid.

**Units:**
- Blue: Captain Mifune (APU pilot, high ATK, ranged), Zee (infantry,
  rocket launcher), 6× APU pilots (ranged, slow, high HP),
  4× Zion infantry (light), Niobe (fast, must reach the
  power terminal)
- Red: 20× Sentinels (flying, swarm, low HP each but many),
  2× Sentinel clusters (heavy, high HP), Drilling machine
  (massive, slow, breaches wall)

**Win conditions:**
- Blue: Niobe reaches the power terminal (reach_tile) OR survive
  to turn 15 (Neo makes peace with the machines)
- Red: overwhelm all APUs OR drilling machine reaches core (reach_tile)

**Special:** Sentinels can fly (ignore terrain). APUs are stationary
turrets (0 MOVE, high ATK). Swarm mechanics — lots of weak enemies.

**Map:** 16×10, Zion dock interior, mechanical/industrial terrain.

---

### 11. Burly Brawl (Neo vs Smiths)
**Blue:** Neo (single powerful unit)
**Red:** Agent Smith copies (many)

**Plot:** Neo fights 100 copies of Agent Smith in the courtyard.

**Units:**
- Blue: Neo (1 unit — massive HP, massive ATK, SPD 12, can attack
  multiple adjacent targets per turn via plugin)
- Red: 16× Agent Smith (moderate stats, respawn mechanic — when
  killed, a new Smith spawns at red's edge next turn)

**Win conditions:**
- Blue: survive 15 turns (Neo eventually flies away)
  → `protect_unit_survives`
- Red: kill Neo (bring HP to 0)

**Special:** Neo can "multi-attack" (plugin: attack hits all adjacent
enemies). Smiths respawn — killing them is temporary. The challenge
is attrition. Small, tight map.

**Map:** 10×10, courtyard, benches as obstacles.

---

## Naruto

### 12. Pain's Assault on Konoha
**Blue:** Konoha defenders
**Red:** The Six Paths of Pain

**Plot:** Pain (Nagato) attacks the Hidden Leaf Village with his
six bodies. Naruto arrives in Sage Mode as reinforcement.

**Units:**
- Blue: Kakashi (jonin, mage, Sharingan), Tsunade (mage, healer),
  Choji (heavy infantry), Shikamaru (tactician — debuff aura),
  6× Konoha chunin, 2× ANBU (assassin)
  → Naruto (Sage Mode) spawns turn 8 as reinforcement
- Red: Deva Path (gravity push — ranged AOE), Animal Path (summons),
  Asura Path (ranged missiles), Human Path (soul steal — instant
  kill on adjacent), Preta Path (absorbs magic — high RES), Naraka
  Path (healer — can revive one dead Path per turn via plugin)

**Win conditions:**
- Blue: destroy ALL six Paths (they share a linked health pool?
  Or kill each individually — Naraka can revive so kill Naraka first)
- Red: capture Naruto (after he spawns) OR eliminate all defenders

**Special:** Each Path has a unique ability. Naraka Path can revive
one dead Path per turn (plugin). Naruto arrives turn 8 as a powerful
reinforcement (sage mode — high everything). Chibaku Tensei
terrain event at turn 10 (Deva Path reshapes the battlefield).

**Map:** 16×14, Konoha village, buildings as cover, Hokage monument
in background.

---

### 13. Fourth Ninja War — Madara Unleashed
**Blue:** Allied Shinobi Forces
**Red:** Madara Uchiha + Reanimated army

**Plot:** Madara Uchiha is reanimated and single-handedly takes on
the entire Shinobi Alliance.

**Units:**
- Blue: Naruto (sage, high ATK), Gaara (sand shield — high DEF,
  ranged), Onoki (flight, ranged), Tsunade (healer), A (Raikage,
  fast, high ATK), Mei (mage, ranged), 8× Allied shinobi
- Red: Madara (VIP — massively OP, Susanoo gives him +10 DEF,
  ranged, magic, can attack twice per turn), 8× White Zetsu (weak
  clones, swarm), 2× Reanimated ninja (strong)

**Win conditions:**
- Blue: survive until turn cap (sealing jutsu preparation)
  → `protect_unit_survives` for any blue VIP
- Red: eliminate all blue units (Madara is trying to wipe them out)

**Special:** Madara is intentionally overpowered (ATK 18, DEF 12,
HP 60). The challenge for blue is managing a force-of-nature enemy.
Blue wins by endurance, not by killing Madara.

**Map:** 14×12, rocky battlefield, desert terrain.

---

### 14. Valley of the End (Naruto vs Sasuke)
**Blue:** Naruto
**Red:** Sasuke

**Plot:** The final confrontation between Naruto and Sasuke at the
Valley of the End waterfall statues.

**Units:**
- Blue: Naruto (1 unit — sage mode + nine-tails, HP 50, ATK 14,
  can_heal self +5/turn via plugin)
- Red: Sasuke (1 unit — Rinnegan + Susanoo, HP 50, ATK 15,
  ranged 1-2, magic)

**Win conditions:**
- Both: reduce opponent to 0 HP. No elimination — 1v1 duel.
- Draw at turn cap (historically they fought to mutual exhaustion)

**Special:** 1v1 duel scenario. Both units are roughly equal. The
waterfall in the center provides terrain bonuses. Statues as
impassable terrain flanking the arena.

**Map:** 8×6, small arena, waterfall center, statue cliffs on sides.

---

## One Piece

### 15. Battle of Marineford (Summit War)
**Blue:** Whitebeard Pirates (rescuing Ace)
**Red:** Marines + Warlords

**Plot:** Whitebeard's crew assaults Marineford to rescue Ace from
execution.

**Units:**
- Blue: Whitebeard (VIP, massive HP 60, earthquake ATK — ranged),
  Marco (phoenix, can_heal, flying), Jozu (diamond body — highest
  DEF), Vista (swordsman), Ace (prisoner — starts immobilized at
  execution platform, freed at turn 6 via plugin), 8× Whitebeard
  commanders
- Red: Akainu (admiral, lava fist — highest ATK), Aokiji (admiral,
  ice — ranged), Kizaru (admiral, light speed — highest SPD),
  Sengoku (fleet admiral), Garp (hero — conflicted, reduced ATK),
  Mihawk (warlord, swordsman), 8× Marine captains

**Win conditions:**
- Blue: free Ace (reach execution platform, turn ≥ 6) AND get Ace
  to the south edge (reach_goal_line) — compound plugin
- Red: execute Ace (kill him after freed) OR kill Whitebeard

**Special:** Ace is frozen/immobilized until turn 6 (key turns). Once
freed, he joins blue as a powerful fire-user but at low HP. The three
admirals are each elite — one of the hardest scenarios. Ice terrain
from Aokiji's power freezes the bay.

**Map:** 18×14, Marineford plaza, execution platform at north center,
bay (frozen water) at south, Marine HQ buildings.

---

### 16. Enies Lobby (Rescue Robin)
**Blue:** Straw Hat Pirates
**Red:** CP9 + Marines

**Plot:** The Straw Hats assault the judicial island to save Robin.
Each crew member fights their CP9 counterpart.

**Units:**
- Blue: Luffy (rubber, high HP, fast, melee), Zoro (swordsman, 3
  swords — highest ATK), Sanji (kicker, fast, melee), Nami (weather
  mage, ranged), Usopp (sniper, ranged 3-5), Chopper (healer +
  monster point transformation plugin), Franky (cyborg, ranged +
  melee, high DEF)
- Red: Lucci (leopard, highest ATK), Kaku (giraffe, ranged), Jabra
  (wolf, fast), Blueno (door — can teleport via plugin), Kumadori
  (life return), Fukuro (zipper), Kalifa (bubble — debuff),
  Spandam (weak commander, has Robin hostage)

**Win conditions:**
- Blue: rescue Robin (reach Spandam's tile) + reach the escape ship
  (reach_tile south edge)
- Red: kill any Straw Hat (they never lose a member — this is the
  stakes) OR prevent rescue for turn cap

**Map:** 14×10, Bridge of Hesitation spanning the gap, Tower of
Justice on one side, escape route on the other.

---

## Additional Franchises

### 17. Star Wars — Battle of Hoth
**Blue:** Rebel Alliance (defending Echo Base)
**Red:** Imperial Army (Blizzard Force)

**Units:**
- Blue: Luke Skywalker (pilot, snowspeeder — fast, tow cable
  ability), Han Solo (gunslinger, ranged), Leia (commander — aura
  +2 ATK to adjacent), 4× Rebel soldiers, 2× snowspeeders (fast,
  ranged), 2× turrets (stationary, high ATK, ranged 3-5)
- Red: General Veers (AT-AT commander), 4× AT-ATs (massive HP 50,
  slow MOVE 1, ranged, DEF 15), 6× snowtroopers (infantry),
  2× AT-STs (medium walkers)

**Win conditions:**
- Blue: evacuate 3 transports (3× reach_tile at escape point) OR
  survive to turn 15 (shields hold long enough)
- Red: destroy the shield generator (reach_tile) OR eliminate all
  rebels

**Special:** AT-ATs are nearly invulnerable from front (DEF 15) but
weak from behind (DEF 4, requires flanking — plugin). Tow cable
mechanic for snowspeeders. Snow/ice terrain throughout.

**Map:** 16×12, snowy field, Echo Base at south, AT-ATs approaching
from north.

---

### 18. Avatar: TLA — Siege of the North
**Blue:** Northern Water Tribe
**Red:** Fire Nation invasion fleet

**Plot:** Admiral Zhao's fleet attacks the North Pole. Aang enters
the Avatar State and devastates the fleet with the Ocean Spirit.

**Units:**
- Blue: Aang (avatar, mage, high everything, but starts weak —
  powers up at turn 10 via plugin), Katara (waterbender, healer +
  ranged), Sokka (warrior, tactician), Pakku (master waterbender),
  6× Water Tribe warriors, 2× waterbenders
- Red: Admiral Zhao (firebender, VIP), Zuko (firebender, conflicted),
  8× Fire Nation soldiers, 4× firebenders, 2× komodo rhino cavalry

**Win conditions:**
- Blue: protect the Spirit Oasis (hold_tile) AND survive to turn 10
  (Avatar State activates → auto-win)
- Red: reach the Spirit Oasis (reach_tile) AND kill the Moon Spirit
  (special unit at the oasis) before turn 10

**Special:** Aang transform at turn 10 — becomes invulnerable
one-shot-everything (narrative victory, not fair combat). Water
terrain boosts waterbenders (+3 ATK). Night terrain at turn 6
(eclipse removes firebender bonuses).

**Map:** 16×10, ice fortress, canals (water terrain), Spirit Oasis
at blue's rear.

---

### 19. Attack on Titan — Battle of Trost
**Blue:** Survey Corps + Garrison
**Red:** Titans

**Plot:** Titans breach Wall Rose at Trost district. Eren transforms
into the Attack Titan. Humanity fights back.

**Units:**
- Blue: Eren (titan shifter — transforms at turn 5, massive HP,
  massive ATK), Mikasa (elite soldier, highest SPD, ATK), Armin
  (tactician, weak but special abilities), Levi (humanity's
  strongest — elite, SPD 14, double attack), 6× Survey Corps
  (ODM gear — ignore terrain, moderate ATK), 4× Garrison soldiers
  (weaker)
- Red: Armored Titan (massive HP 80, DEF 20, slow), Colossal Titan
  (appears turn 1, kicks the wall, then vanishes — terrain
  destruction event), 8× regular Titans (HP 30, slow, melee only,
  weak spot = back), 4× Abnormal Titans (fast, unpredictable)

**Win conditions:**
- Blue: seal the breach (Eren reaches the wall gap tile in titan
  form after turn 5) — reach_tile compound with transform
- Red: eat all blue units (eliminate) OR reach the inner gate
  (reach_tile)

**Special:** ODM gear lets Survey Corps ignore terrain costs. Titans
only take full damage from behind (plugin: front attacks deal 25%
damage). Eren transforms at turn 5 into Attack Titan (stat change).

**Map:** 14×12, Trost district, Wall Rose at south (breach at
center), buildings as terrain, streets as movement lanes.

---

### 20. Demon Slayer — Infinity Castle
**Blue:** Demon Slayer Corps (Hashira)
**Red:** Upper Moon Demons + Muzan

**Plot:** The final assault on Muzan's Infinity Castle. All Hashira
deploy against the remaining Upper Moons.

**Units:**
- Blue: Tanjiro (sun breathing, anti-demon bonus), Zenitsu (thunder,
  one devastating attack per turn), Inosuke (beast, dual blade,
  fast), Giyu (water hashira, high DEF), Shinobu (insect hashira,
  poison — damage over time), Mitsuri (love hashira, flexible range),
  6× Demon Slayer Corps members
- Red: Muzan (VIP, regeneration +5 HP/turn, highest ATK), Akaza
  (Upper 3, martial arts, high SPD), Doma (Upper 2, ice, mage),
  Kokushibo (Upper 1, moon breathing, strongest swordsman),
  4× Lower Moon demons

**Win conditions:**
- Blue: kill Muzan (requires sunlight — Muzan dies if alive at
  turn cap when "dawn" arrives, so blue just needs to survive
  while weakening him) → `protect_unit_survives` + plugin for
  dawn mechanic
- Red: kill Tanjiro OR eliminate all Hashira

**Special:** Demons regenerate HP each turn (plugin). Nichirin
swords (blue's weapons) prevent regeneration on hit (damage
is permanent). Dawn at turn 20 — Muzan takes 99 damage per turn
from sunlight. The Infinity Castle shifts — random terrain changes
every 3 turns.

**Map:** 16×12, multi-level castle interior, shifting architecture
(terrain mutation plugin), wisteria barriers as terrain.

---

## Summary Table

| # | Source | Scenario | Blue | Red | Key Mechanic |
|---|---|---|---|---|---|
| 1 | GoT | Battle of the Bastards | Starks | Boltons | Reinforcement (Vale) |
| 2 | GoT | The Long Night | Living | Dead | Kill-one-win-all (Night King) |
| 3 | GoT | Blackwater Bay | Stannis | Lannisters | Wildfire terrain + reinforcement |
| 4 | GoT | Loot Train Attack | Dothraki+Dragon | Lannisters | Dragon (flying ranged) |
| 5 | HP | Battle of Hogwarts | Order | Death Eaters | All-mage + Horcrux mechanic |
| 6 | HP | Dept of Mysteries | DA | Death Eaters | Indoor + reinforcement |
| 7 | HP | Astronomy Tower | Dumbledore | Death Eaters | Betrayal (Snape switch) |
| 8 | LotR | Pelennor Fields | Gondor+Rohan | Mordor | Cavalry reinforcement + terror |
| 9 | LotR | Amon Hen | Fellowship | Uruk-hai | Protect hobbits escort |
| 10 | Matrix | Zion Dock | Humans | Sentinels | Turret defense + swarm |
| 11 | Matrix | Burly Brawl | Neo (solo) | 100 Smiths | Respawn + multi-attack |
| 12 | Naruto | Pain's Assault | Konoha | Six Paths | Unique path abilities + revive |
| 13 | Naruto | Madara Unleashed | Alliance | Madara | Overpowered boss + survival |
| 14 | Naruto | Valley of the End | Naruto | Sasuke | 1v1 duel |
| 15 | One Piece | Marineford | Whitebeard | Marines | Prisoner rescue compound |
| 16 | One Piece | Enies Lobby | Straw Hats | CP9 | Hostage rescue + escape |
| 17 | Star Wars | Battle of Hoth | Rebels | Empire | AT-AT vulnerability + evac |
| 18 | Avatar | Siege of the North | Water Tribe | Fire Nation | Avatar State transform |
| 19 | AoT | Battle of Trost | Survey Corps | Titans | Titan shifting + directional damage |
| 20 | Demon Slayer | Infinity Castle | Hashira | Demons | Regeneration + dawn countdown |
