"""
vetgpt/backend/schedule_templates.py

Veterinary schedule templates.

Each template defines a series of events relative to a start date.
The LLM uses these as reference when generating custom schedules,
but can also override/extend them based on user context.

Sources:
  - Poultry vaccination: FAO, Kenya Veterinary Board guidelines
  - Cattle reproduction: Merck Veterinary Manual
  - Small ruminants: FAO Livestock Manuals
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ScheduleEvent:
    day_offset:   int           # days from start_date (0 = start_date)
    title:        str
    description:  str
    critical:     bool = False  # critical = alert 2 days before AND on the day
    reminder_days: list[int] = None  # days before to send reminder e.g. [3, 1, 0]

    def __post_init__(self):
        if self.reminder_days is None:
            self.reminder_days = [1, 0]  # default: day before + day of


@dataclass
class ScheduleTemplate:
    key:         str
    name:        str
    species:     str
    description: str
    events:      list[ScheduleEvent]
    language_variants: dict[str, str] = None  # key=lang_code, value=name in that language

    def __post_init__(self):
        if self.language_variants is None:
            self.language_variants = {}


# ─── Poultry ──────────────────────────────────────────────────────────────────

CHICK_VACCINATION = ScheduleTemplate(
    key         = "chick_vaccination",
    name        = "Day-Old Chick Vaccination Schedule",
    species     = "poultry",
    description = "Standard vaccination schedule for broilers and layers from day of purchase",
    language_variants = {
        "sw": "Ratiba ya Chanjo kwa Vifaranga",
    },
    events      = [
        ScheduleEvent(
            day_offset  = 0,
            title       = "Day 1 — Marek's Disease (if not vaccinated at hatchery)",
            description = "Administer Marek's disease vaccine subcutaneously if chicks did not receive it at hatchery. Most commercial chicks are vaccinated at hatchery — confirm with supplier.",
            critical    = True,
            reminder_days = [0],
        ),
        ScheduleEvent(
            day_offset  = 7,
            title       = "Day 7 — Newcastle Disease (HB1/LaSota) + Infectious Bronchitis",
            description = "Administer Newcastle Disease vaccine (HB1 or Hitchner B1 strain) via eye drop or drinking water. Combine with Infectious Bronchitis vaccine (Massachusetts strain) if available. Withhold water 2 hours before vaccination.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 14,
            title       = "Day 14 — Gumboro (IBD) First Dose",
            description = "Administer Infectious Bursal Disease (Gumboro) vaccine via drinking water. Use intermediate strain for broilers, mild strain for layers. Withhold water 1-2 hours before. Clean all drinkers.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 21,
            title       = "Day 21 — Newcastle Disease Second Dose (LaSota)",
            description = "Booster Newcastle Disease vaccination using LaSota strain via drinking water or spray. Also check for signs of coccidiosis — start anticoccidial if not using medicated feed.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 28,
            title       = "Day 28 — Gumboro Second Dose",
            description = "Second dose of IBD (Gumboro) vaccine. Critical for full immunity. Use intermediate plus strain if disease pressure is high in your area.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 35,
            title       = "Day 35 — Fowl Pox (layers only)",
            description = "Administer Fowl Pox vaccine via wing web stab method for layer chicks. Not required for broilers (slaughtered before 6 weeks). Check wing for 'take' reaction at day 7 post-vaccination.",
            critical    = False,
            reminder_days = [1, 0],
        ),
        ScheduleEvent(
            day_offset  = 42,
            title       = "Day 42 — Newcastle Disease Third Dose + Health Check",
            description = "Third Newcastle booster using LaSota via drinking water. Full flock health assessment. Weigh a sample of birds and compare to breed standard. Adjust feed program if needed.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 60,
            title       = "Day 60 — Egg Drop Syndrome + Infectious Coryza (layers)",
            description = "For layer pullets: administer killed EDS-76 vaccine and Infectious Coryza vaccine IM. This is 4 weeks before expected point of lay. Not applicable for broilers.",
            critical    = False,
            reminder_days = [3, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 112,
            title       = "Week 16 — Pre-lay Newcastle + IB Booster (layers)",
            description = "Final pre-production booster: killed Newcastle + Infectious Bronchitis bivalent vaccine IM. Ensure all birds are vaccinated before 18 weeks.",
            critical    = False,
            reminder_days = [3, 1, 0],
        ),
    ],
)


# ─── Cattle reproduction ──────────────────────────────────────────────────────

CATTLE_HEAT_MONITORING = ScheduleTemplate(
    key         = "cattle_heat_monitoring",
    name        = "Cattle Oestrus (Heat) Monitoring Schedule",
    species     = "cattle",
    description = "21-day cycle monitoring from observed or synchronized heat",
    language_variants = {
        "sw": "Ratiba ya Ufuatiliaji wa Joto (Heat) kwa Ng'ombe",
    },
    events      = [
        ScheduleEvent(
            day_offset  = 0,
            title       = "Day 0 — Heat Observed / AI performed",
            description = "Record time of heat detection. If AI: note bull/semen batch. Optimal insemination: 12-18 hours after onset of standing heat.",
            critical    = True,
            reminder_days = [0],
        ),
        ScheduleEvent(
            day_offset  = 18,
            title       = "Day 18 — Begin heat watch (next expected cycle)",
            description = "Begin intensive heat detection. Watch morning and evening for 30 minutes each. Signs: standing to be mounted, restlessness, clear mucus discharge, reduced milk.",
            critical    = True,
            reminder_days = [1, 0],
        ),
        ScheduleEvent(
            day_offset  = 21,
            title       = "Day 21 — Expected return to heat (if not pregnant)",
            description = "If cow returns to heat: AI failed or repeat breeding required. If no heat: encouraging sign of pregnancy. Do not assume pregnancy — confirm by rectal palpation or ultrasonography at day 28-35.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 28,
            title       = "Day 28-35 — Pregnancy diagnosis",
            description = "Earliest reliable pregnancy confirmation by ultrasonography (day 25-28) or rectal palpation (day 35+). Blood or milk progesterone test at day 21-24 is an alternative.",
            critical    = True,
            reminder_days = [2, 1, 0],
        ),
        ScheduleEvent(
            day_offset  = 270,
            title       = "Day 270 — Expected calving (9 months)",
            description = "Move cow to calving pen. Prepare calving kit. Monitor for signs: relaxation of pelvic ligaments, swollen vulva, milk in udder, restlessness. Have dystocia kit and colostrum supplement ready.",
            critical    = True,
            reminder_days = [14, 7, 3, 1, 0],
        ),
    ],
)

CATTLE_DEWORMING = ScheduleTemplate(
    key         = "cattle_deworming",
    name        = "Cattle Deworming Schedule",
    species     = "cattle",
    description = "Strategic deworming programme for beef and dairy cattle",
    language_variants = {"sw": "Ratiba ya Dawa ya Minyoo kwa Ng'ombe"},
    events      = [
        ScheduleEvent(day_offset=0,   title="Day 0 — Initial deworming",       description="Administer broad-spectrum anthelmintic (e.g. Albendazole 7.5mg/kg or Ivermectin 0.2mg/kg). Withhold milk for withdrawal period. Record product and batch number.", critical=True, reminder_days=[1,0]),
        ScheduleEvent(day_offset=90,  title="Day 90 — Second treatment",        description="Repeat deworming, ideally rotating drug class to prevent resistance. Use Levamisole or Fenbendazole if previous treatment was Ivermectin-based.", critical=False, reminder_days=[3,1,0]),
        ScheduleEvent(day_offset=180, title="Day 180 — Third treatment",         description="Pre-rainy season deworming. Consider faecal egg count (FEC) to assess worm burden before treating — avoid unnecessary treatments.", critical=False, reminder_days=[3,1,0]),
        ScheduleEvent(day_offset=270, title="Day 270 — Post-rainy season check", description="FEC check and treat if egg count exceeds threshold (typically >200 EPG for beef, >150 for dairy). Pay attention to periparturient cows.", critical=False, reminder_days=[3,1,0]),
    ],
)

# ─── Small ruminants ──────────────────────────────────────────────────────────

GOAT_SHEEP_VACCINATION = ScheduleTemplate(
    key         = "goat_sheep_vaccination",
    name        = "Goat/Sheep Vaccination Schedule",
    species     = "ovine_caprine",
    description = "Core vaccination programme for goats and sheep",
    language_variants = {"sw": "Ratiba ya Chanjo kwa Mbuzi/Kondoo"},
    events      = [
        ScheduleEvent(day_offset=0,   title="Day 0 — PPR (Peste des Petits Ruminants)",  description="Administer PPR vaccine (Nigeria 75/1 strain) subcutaneously. Single dose, protects for 3 years. Priority vaccination especially in East Africa where PPR is endemic.", critical=True, reminder_days=[1,0]),
        ScheduleEvent(day_offset=30,  title="Day 30 — Foot and Mouth Disease (FMD)",      description="FMD vaccine (appropriate local strains). Two doses 4 weeks apart initially, then 6-monthly. Verify current circulating strains with local vet authority.", critical=True, reminder_days=[2,1,0]),
        ScheduleEvent(day_offset=60,  title="Day 60 — FMD Second Dose",                   description="Second FMD dose to complete primary course.", critical=True, reminder_days=[2,1,0]),
        ScheduleEvent(day_offset=180, title="6 Months — Enterotoxaemia (Clostridial)",    description="Administer Clostridium perfringens type C+D toxoid. Two doses 4-6 weeks apart initially, then annually. Critical before weaning season.", critical=False, reminder_days=[3,1,0]),
        ScheduleEvent(day_offset=365, title="Annual — Booster vaccinations",               description="Annual boosters: PPR (if local authority recommends), FMD, Enterotoxaemia. Check Kenya Veterinary Board current schedule for required vaccines.", critical=False, reminder_days=[7,3,0]),
    ],
)

# ─── Template registry ────────────────────────────────────────────────────────

SCHEDULE_TEMPLATES: dict[str, ScheduleTemplate] = {
    "chick_vaccination":      CHICK_VACCINATION,
    "cattle_heat_monitoring": CATTLE_HEAT_MONITORING,
    "cattle_deworming":       CATTLE_DEWORMING,
    "goat_sheep_vaccination": GOAT_SHEEP_VACCINATION,
}


def get_template(key: str) -> Optional[ScheduleTemplate]:
    return SCHEDULE_TEMPLATES.get(key)


def templates_for_species(species: str) -> list[ScheduleTemplate]:
    return [t for t in SCHEDULE_TEMPLATES.values() if t.species == species]


def all_template_keys() -> list[str]:
    return list(SCHEDULE_TEMPLATES.keys())