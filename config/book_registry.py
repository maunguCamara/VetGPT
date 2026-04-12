"""
vetgpt/config/book_registry.py

Master registry of all veterinary reference books in the VetGPT corpus.

Each entry defines:
- Canonical title and authors
- Publisher and edition
- Legal status (open, licensed, pending)
- Citation format
- Filename patterns for auto-detection from PDF filename
- Subject tags for filtering

Usage:
    from config.book_registry import BOOK_REGISTRY, get_book_metadata, detect_book

    # Auto-detect from filename
    meta = detect_book("fossum_small_animal_surgery_4e.pdf")

    # Look up by key
    meta = BOOK_REGISTRY["plumbs"]

    # Get ChromaDB-ready metadata dict
    chroma_meta = get_book_metadata("plumbs")
"""

from dataclasses import dataclass, field
from typing import Optional
import re

# Legal status constants
OPEN_ACCESS   = "open_access"       # Free to use, scrape, index
LICENSED      = "licensed"          # You have a license agreement
PENDING       = "pending_license"   # Negotiating with publisher
PERSONAL      = "personal_use"      # Bought copy, personal/research use only
RESTRICTED    = "restricted"        # Do not index without explicit license


@dataclass
class BookMeta:
    """Full metadata for a single veterinary reference book."""

    # Identity
    key: str                        # short unique key e.g. "plumbs"
    title: str                      # full canonical title
    short_title: str                # abbreviated title for citations
    authors: list[str]              # primary authors/editors
    edition: str                    # e.g. "9th Edition"
    year: str                       # publication year of this edition

    # Publisher
    publisher: str
    publisher_short: str            # e.g. "Elsevier"
    isbn: str = ""

    # Legal
    legal_status: str = PENDING
    license_contact: str = ""       # who to contact for licensing
    license_url: str = ""

    # Content
    subject_tags: list[str] = field(default_factory=list)
    species_tags: list[str] = field(default_factory=list)  # dog, cat, bovine, etc.
    content_type: str = "textbook"  # textbook | manual | handbook | atlas | formulary

    # File detection
    filename_patterns: list[str] = field(default_factory=list)  # regex patterns

    # Citation
    citation_format: str = ""       # APA-style citation template

    def to_chroma_metadata(self, page_number: int = 1, chunk_index: int = 0) -> dict:
        """
        Return a ChromaDB-compatible metadata dict.
        All values must be str, int, float, or bool.
        """
        return {
            "document_title": self.title,
            "short_title": self.short_title,
            "authors": ", ".join(self.authors[:3]),
            "edition": self.edition,
            "year": self.year,
            "publisher": self.publisher,
            "publisher_short": self.publisher_short,
            "isbn": self.isbn,
            "legal_status": self.legal_status,
            "subject_tags": ", ".join(self.subject_tags),
            "species_tags": ", ".join(self.species_tags),
            "content_type": self.content_type,
            "source": "pdf",
            "source_file": self.key,
            "page_number": page_number,
            "chunk_index": chunk_index,
            "has_tables": False,
            "has_images": False,
            "citation": self.citation_format,
        }

    def cite(self, page: Optional[int] = None) -> str:
        """Generate a formatted citation string."""
        base = self.citation_format
        if page:
            base += f" p. {page}"
        return base


# ==============================================================================
# THE REGISTRY
# ==============================================================================

BOOK_REGISTRY: dict[str, BookMeta] = {

    # -------------------------------------------------------------------------
    # CORE REFERENCES
    # -------------------------------------------------------------------------

    "merck_vet": BookMeta(
        key="merck_vet",
        title="Merck Veterinary Manual",
        short_title="Merck Vet Manual",
        authors=["Merck & Co."],
        edition="12th Edition",
        year="2023",
        publisher="Merck & Co., Inc.",
        publisher_short="Merck",
        legal_status=PENDING,
        license_contact="veterinarymanual@merck.com",
        license_url="https://www.merckvetmanual.com",
        subject_tags=["general", "diseases", "treatment", "diagnosis", "pharmacology"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine", "poultry", "exotic"],
        content_type="manual",
        filename_patterns=[r"merck.*vet", r"msd.*vet", r"merck.*manual"],
        citation_format="Merck Veterinary Manual, 12th Ed. (2023). Merck & Co.",
    ),

    "msd_vet": BookMeta(
        key="msd_vet",
        title="MSD Veterinary Manual",
        short_title="MSD Vet Manual",
        authors=["MSD Animal Health"],
        edition="12th Edition",
        year="2023",
        publisher="Merck Sharp & Dohme Corp.",
        publisher_short="MSD",
        legal_status=PENDING,
        license_contact="veterinarymanual@merck.com",
        license_url="https://www.msdvetmanual.com",
        subject_tags=["general", "diseases", "treatment", "diagnosis"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine", "poultry"],
        content_type="manual",
        filename_patterns=[r"msd.*vet", r"msd.*manual"],
        citation_format="MSD Veterinary Manual, 12th Ed. (2023). MSD Animal Health.",
    ),

    "blackwells_5min": BookMeta(
        key="blackwells_5min",
        title="Blackwell's Five-Minute Veterinary Consult: Canine and Feline",
        short_title="Blackwell's 5-Min Vet Consult",
        authors=["Tilley, L.P.", "Smith, F.W.K."],
        edition="7th Edition",
        year="2021",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-1119513179",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        license_url="https://www.wiley.com/en-us/permissions",
        subject_tags=["clinical", "diagnosis", "treatment", "quick reference"],
        species_tags=["dog", "cat"],
        content_type="manual",
        filename_patterns=[r"blackwell.*five.*min", r"5.*min.*vet", r"five.*minute.*vet"],
        citation_format="Tilley & Smith. Blackwell's Five-Minute Veterinary Consult, 7th Ed. (2021). Wiley-Blackwell.",
    ),

    # -------------------------------------------------------------------------
    # CLINICAL & DIAGNOSTIC
    # -------------------------------------------------------------------------

    "clinical_vet_advisor": BookMeta(
        key="clinical_vet_advisor",
        title="Clinical Veterinary Advisor: Dogs and Cats",
        short_title="Clinical Vet Advisor",
        authors=["Côté, E."],
        edition="3rd Edition",
        year="2015",
        publisher="Elsevier Mosby",
        publisher_short="Elsevier",
        isbn="978-0323226219",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        license_url="https://www.elsevier.com/about/policies/copyright/permissions",
        subject_tags=["clinical", "diagnosis", "treatment", "procedures"],
        species_tags=["dog", "cat"],
        content_type="manual",
        filename_patterns=[r"clinical.*vet.*advisor", r"cote.*advisor"],
        citation_format="Côté, E. Clinical Veterinary Advisor: Dogs and Cats, 3rd Ed. (2015). Elsevier.",
    ),

    "saunders_dict": BookMeta(
        key="saunders_dict",
        title="Saunders Comprehensive Veterinary Dictionary",
        short_title="Saunders Vet Dictionary",
        authors=["Blood, D.C.", "Studdert, V.P.", "Gay, C.C."],
        edition="4th Edition",
        year="2011",
        publisher="Saunders Elsevier",
        publisher_short="Elsevier",
        isbn="978-0702028557",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["terminology", "dictionary", "definitions"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine"],
        content_type="handbook",
        filename_patterns=[r"saunders.*vet.*dict", r"vet.*dictionary"],
        citation_format="Blood et al. Saunders Comprehensive Veterinary Dictionary, 4th Ed. (2011). Elsevier.",
    ),

    "radostits_large_animal": BookMeta(
        key="radostits_large_animal",
        title="Veterinary Medicine: A Textbook of the Diseases of Cattle, Horses, Sheep, Pigs and Goats",
        short_title="Radostits Veterinary Medicine",
        authors=["Radostits, O.M.", "Gay, C.C.", "Hinchcliff, K.W.", "Constable, P.D."],
        edition="10th Edition",
        year="2006",
        publisher="Saunders Elsevier",
        publisher_short="Elsevier",
        isbn="978-0702027772",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["large animal", "diseases", "medicine", "diagnosis", "treatment"],
        species_tags=["bovine", "equine", "ovine", "caprine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"radostits", r"vet.*med.*cattle.*horse", r"diseases.*cattle"],
        citation_format="Radostits et al. Veterinary Medicine, 10th Ed. (2006). Elsevier.",
    ),

    # -------------------------------------------------------------------------
    # CLINICAL PROCEDURES
    # -------------------------------------------------------------------------

    "crow_walshaw": BookMeta(
        key="crow_walshaw",
        title="Manual of Clinical Procedures in Dogs, Cats, Rabbits and Rodents",
        short_title="Crow & Walshaw Clinical Procedures",
        authors=["Crow, S.E.", "Walshaw, S.O."],
        edition="3rd Edition",
        year="1997",
        publisher="Lippincott Williams & Wilkins",
        publisher_short="LWW",
        isbn="978-0397514601",
        legal_status=PERSONAL,
        subject_tags=["clinical procedures", "techniques", "practical"],
        species_tags=["dog", "cat", "rabbit", "rodent"],
        content_type="manual",
        filename_patterns=[r"crow.*walshaw", r"manual.*clinical.*proc"],
        citation_format="Crow & Walshaw. Manual of Clinical Procedures, 3rd Ed. (1997). LWW.",
    ),

    "manual_operative_surgery": BookMeta(
        key="manual_operative_surgery",
        title="Manual of Operative Veterinary Surgery",
        short_title="Manual of Operative Vet Surgery",
        authors=["Liautard, A."],
        edition="Classic Edition",
        year="1892",
        publisher="D. Appleton & Co.",
        publisher_short="Appleton",
        legal_status=OPEN_ACCESS,   # Pre-1928, public domain
        subject_tags=["surgery", "operative", "procedures"],
        species_tags=["bovine", "equine", "dog"],
        content_type="manual",
        filename_patterns=[r"manual.*operative.*vet", r"liautard"],
        citation_format="Liautard, A. Manual of Operative Veterinary Surgery. D. Appleton & Co. [Public Domain]",
    ),

    # -------------------------------------------------------------------------
    # SMALL ANIMAL
    # -------------------------------------------------------------------------

    "nelson_couto_small_animal": BookMeta(
        key="nelson_couto_small_animal",
        title="Small Animal Internal Medicine",
        short_title="Nelson & Couto Small Animal Internal Medicine",
        authors=["Nelson, R.W.", "Couto, C.G."],
        edition="6th Edition",
        year="2019",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0323554237",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["internal medicine", "diagnosis", "treatment"],
        species_tags=["dog", "cat"],
        content_type="textbook",
        filename_patterns=[r"nelson.*couto", r"small.*animal.*internal.*med"],
        citation_format="Nelson & Couto. Small Animal Internal Medicine, 6th Ed. (2019). Elsevier.",
    ),

    "fossum_surgery": BookMeta(
        key="fossum_surgery",
        title="Small Animal Surgery",
        short_title="Fossum Small Animal Surgery",
        authors=["Fossum, T.W."],
        edition="5th Edition",
        year="2018",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0323442794",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["surgery", "surgical procedures", "anesthesia"],
        species_tags=["dog", "cat"],
        content_type="textbook",
        filename_patterns=[r"fossum", r"small.*animal.*surg"],
        citation_format="Fossum, T.W. Small Animal Surgery, 5th Ed. (2018). Elsevier.",
    ),

    "bsava_canine_feline": BookMeta(
        key="bsava_canine_feline",
        title="BSAVA Manual of Canine and Feline Practice",
        short_title="BSAVA Manual",
        authors=["BSAVA"],
        edition="Current Edition",
        year="2022",
        publisher="British Small Animal Veterinary Association",
        publisher_short="BSAVA",
        legal_status=PENDING,
        license_contact="publications@bsava.com",
        license_url="https://www.bsava.com/publications",
        subject_tags=["clinical practice", "diagnosis", "treatment"],
        species_tags=["dog", "cat"],
        content_type="manual",
        filename_patterns=[r"bsava.*manual", r"bsava.*canine.*feline"],
        citation_format="BSAVA Manual of Canine and Feline Practice. BSAVA.",
    ),

    # -------------------------------------------------------------------------
    # LARGE ANIMAL / LIVESTOCK
    # -------------------------------------------------------------------------

    "bovine_medicine": BookMeta(
        key="bovine_medicine",
        title="Bovine Medicine: Diseases and Husbandry of Cattle",
        short_title="Bovine Medicine",
        authors=["Andrews, A.H.", "Blowey, R.W.", "Boyd, H.", "Eddy, R.G."],
        edition="2nd Edition",
        year="2004",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0632055616",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["bovine", "cattle", "diseases", "husbandry"],
        species_tags=["bovine"],
        content_type="textbook",
        filename_patterns=[r"bovine.*med", r"diseases.*husbandry.*cattle"],
        citation_format="Andrews et al. Bovine Medicine, 2nd Ed. (2004). Wiley-Blackwell.",
    ),

    "sheep_goat_medicine": BookMeta(
        key="sheep_goat_medicine",
        title="Sheep and Goat Medicine",
        short_title="Sheep & Goat Medicine",
        authors=["Pugh, D.G.", "Baird, A.N."],
        edition="2nd Edition",
        year="2012",
        publisher="Elsevier Saunders",
        publisher_short="Elsevier",
        isbn="978-1437723007",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["ovine", "caprine", "diseases", "medicine"],
        species_tags=["ovine", "caprine"],
        content_type="textbook",
        filename_patterns=[r"sheep.*goat.*med", r"pugh.*baird"],
        citation_format="Pugh & Baird. Sheep and Goat Medicine, 2nd Ed. (2012). Elsevier.",
    ),

    "equine_internal_medicine": BookMeta(
        key="equine_internal_medicine",
        title="Equine Internal Medicine",
        short_title="Equine Internal Medicine",
        authors=["Reed, S.M.", "Bayly, W.M.", "Sellon, D.C."],
        edition="4th Edition",
        year="2017",
        publisher="Elsevier Saunders",
        publisher_short="Elsevier",
        isbn="978-0323443296",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["equine", "internal medicine", "diagnosis", "treatment"],
        species_tags=["equine"],
        content_type="textbook",
        filename_patterns=[r"equine.*internal.*med", r"reed.*bayly"],
        citation_format="Reed et al. Equine Internal Medicine, 4th Ed. (2017). Elsevier.",
    ),

    # -------------------------------------------------------------------------
    # ANATOMY, PHYSIOLOGY & BASIC SCIENCES
    # -------------------------------------------------------------------------

    "dyce_anatomy": BookMeta(
        key="dyce_anatomy",
        title="Textbook of Veterinary Anatomy",
        short_title="Dyce, Sack & Wensing Anatomy",
        authors=["Dyce, K.M.", "Sack, W.O.", "Wensing, C.J.G."],
        edition="4th Edition",
        year="2009",
        publisher="Saunders Elsevier",
        publisher_short="Elsevier",
        isbn="978-1416066071",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["anatomy", "morphology", "structure"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"dyce.*sack", r"vet.*anatomy", r"textbook.*vet.*anat"],
        citation_format="Dyce, Sack & Wensing. Textbook of Veterinary Anatomy, 4th Ed. (2009). Elsevier.",
    ),

    "dukes_physiology": BookMeta(
        key="dukes_physiology",
        title="Duke's Physiology of Domestic Animals",
        short_title="Duke's Physiology",
        authors=["Reece, W.O.", "Erickson, H.H.", "Goff, J.P.", "Uemura, E.E."],
        edition="13th Edition",
        year="2015",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0470958810",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["physiology", "body systems", "function"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "porcine", "poultry"],
        content_type="textbook",
        filename_patterns=[r"duke.*physiol", r"physiol.*domestic.*animal"],
        citation_format="Reece et al. Duke's Physiology of Domestic Animals, 13th Ed. (2015). Wiley.",
    ),

    "cunningham_physiology": BookMeta(
        key="cunningham_physiology",
        title="Cunningham's Textbook of Veterinary Physiology",
        short_title="Cunningham's Physiology",
        authors=["Klein, B.G."],
        edition="6th Edition",
        year="2019",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0323554206",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["physiology", "organ systems", "homeostasis"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"cunningham.*physiol", r"vet.*physiol.*cunningham"],
        citation_format="Klein (ed.). Cunningham's Textbook of Veterinary Physiology, 6th Ed. (2019). Elsevier.",
    ),

    "dellmann_histology": BookMeta(
        key="dellmann_histology",
        title="Dellmann's Textbook of Veterinary Histology",
        short_title="Dellmann's Histology",
        authors=["Eurell, J.A.", "Frappier, B.L."],
        edition="6th Edition",
        year="2006",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0781741484",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["histology", "tissue", "microscopy", "cytology"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"dellmann.*histol", r"vet.*histol"],
        citation_format="Eurell & Frappier. Dellmann's Textbook of Veterinary Histology, 6th Ed. (2006). Wiley.",
    ),

    # -------------------------------------------------------------------------
    # LABORATORY & PATHOLOGY
    # -------------------------------------------------------------------------

    "vet_clinical_pathology": BookMeta(
        key="vet_clinical_pathology",
        title="Veterinary Clinical Pathology: A Case-Based Approach",
        short_title="Veterinary Clinical Pathology",
        authors=["Latimer, K.S."],
        edition="Current Edition",
        year="2011",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-1405159296",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["clinical pathology", "hematology", "biochemistry", "urinalysis", "cytology"],
        species_tags=["dog", "cat", "bovine", "equine"],
        content_type="textbook",
        filename_patterns=[r"vet.*clinical.*pathol", r"latimer.*pathol"],
        citation_format="Latimer, K.S. Veterinary Clinical Pathology, (2011). Wiley.",
    ),

    "jubb_kennedy_palmer": BookMeta(
        key="jubb_kennedy_palmer",
        title="Pathology of Domestic Animals",
        short_title="Jubb, Kennedy & Palmer",
        authors=["Maxie, M.G."],
        edition="6th Edition",
        year="2016",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0702052677",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["pathology", "gross pathology", "histopathology", "necropsy"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "porcine", "caprine"],
        content_type="textbook",
        filename_patterns=[r"jubb.*kennedy", r"pathol.*domestic.*animal", r"maxie.*pathol"],
        citation_format="Maxie (ed.). Jubb, Kennedy & Palmer's Pathology of Domestic Animals, 6th Ed. (2016). Elsevier.",
    ),

    # -------------------------------------------------------------------------
    # ONLINE SOURCES
    # -------------------------------------------------------------------------

    "wikivet": BookMeta(
        key="wikivet",
        title="WikiVet Veterinary Encyclopedia",
        short_title="WikiVet",
        authors=["WikiVet Contributors"],
        edition="Online",
        year="2024",
        publisher="WikiVet",
        publisher_short="WikiVet",
        legal_status=OPEN_ACCESS,
        license_url="https://en.wikivet.net/WikiVet:Copyrights",
        subject_tags=["general", "diseases", "anatomy", "pharmacology", "clinical"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine", "poultry", "exotic"],
        content_type="manual",
        filename_patterns=[r"wikivet"],
        citation_format="WikiVet. (2024). WikiVet Veterinary Encyclopedia. CC BY-SA.",
    ),

    "eclinpath": BookMeta(
        key="eclinpath",
        title="eClinPath — Online Textbook of Veterinary Clinical Pathology",
        short_title="eClinPath",
        authors=["Raskin, R.E.", "et al."],
        edition="Online",
        year="2024",
        publisher="Cornell University College of Veterinary Medicine",
        publisher_short="Cornell CVM",
        legal_status=OPEN_ACCESS,
        license_url="https://eclinpath.com",
        subject_tags=["clinical pathology", "hematology", "biochemistry", "urinalysis"],
        species_tags=["dog", "cat", "bovine", "equine"],
        content_type="manual",
        filename_patterns=[r"eclinpath"],
        citation_format="eClinPath. Cornell University CVM. https://eclinpath.com",
    ),

    "vin": BookMeta(
        key="vin",
        title="Veterinary Information Network (VIN)",
        short_title="VIN",
        authors=["VIN"],
        edition="Online",
        year="2024",
        publisher="Veterinary Information Network",
        publisher_short="VIN",
        legal_status=PENDING,
        license_contact="info@vin.com",
        license_url="https://www.vin.com",
        subject_tags=["clinical", "diagnosis", "treatment", "case discussions"],
        species_tags=["dog", "cat", "bovine", "equine", "exotic"],
        content_type="manual",
        filename_patterns=[r"^vin_"],
        citation_format="Veterinary Information Network (VIN). https://www.vin.com",
    ),

    # -------------------------------------------------------------------------
    # SPECIALISED — BY FIELD
    # -------------------------------------------------------------------------

    "diseases_of_poultry": BookMeta(
        key="diseases_of_poultry",
        title="Diseases of Poultry",
        short_title="Diseases of Poultry",
        authors=["Swayne, D.E."],
        edition="14th Edition",
        year="2020",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-1119371168",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["poultry", "avian diseases", "flock health"],
        species_tags=["poultry", "chicken", "turkey", "duck"],
        content_type="textbook",
        filename_patterns=[r"diseases.*poultry", r"swayne.*poultry"],
        citation_format="Swayne, D.E. Diseases of Poultry, 14th Ed. (2020). Wiley.",
    ),

    "vet_parasitology": BookMeta(
        key="vet_parasitology",
        title="Veterinary Parasitology",
        short_title="Veterinary Parasitology",
        authors=["Taylor, M.A.", "Coop, R.L.", "Wall, R.L."],
        edition="4th Edition",
        year="2015",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0470671627",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["parasitology", "helminths", "protozoa", "ectoparasites", "antiparasitic"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"vet.*parasitol", r"taylor.*parasitol"],
        citation_format="Taylor et al. Veterinary Parasitology, 4th Ed. (2015). Wiley.",
    ),

    "plumbs": BookMeta(
        key="plumbs",
        title="Plumb's Veterinary Drug Handbook",
        short_title="Plumb's Drug Handbook",
        authors=["Plumb, D.C."],
        edition="9th Edition",
        year="2018",
        publisher="Pharmavet Inc. / Wiley",
        publisher_short="Pharmavet",
        isbn="978-1119344452",
        legal_status=PENDING,
        license_contact="info@plumbsveterinarydrugs.com",
        license_url="https://www.plumbsveterinarydrugs.com",
        subject_tags=["pharmacology", "drug dosages", "drug interactions", "prescribing"],
        species_tags=["dog", "cat", "bovine", "equine", "ovine", "caprine", "porcine", "exotic"],
        content_type="handbook",
        filename_patterns=[r"plumb.*drug", r"plumb.*vet.*drug", r"vet.*drug.*handbook"],
        citation_format="Plumb, D.C. Plumb's Veterinary Drug Handbook, 9th Ed. (2018). Pharmavet/Wiley.",
    ),

    "exotic_animal_formulary": BookMeta(
        key="exotic_animal_formulary",
        title="Exotic Animal Formulary",
        short_title="Exotic Animal Formulary",
        authors=["Carpenter, J.W."],
        edition="5th Edition",
        year="2017",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0323442367",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["exotic", "pharmacology", "drug dosages", "formulary"],
        species_tags=["exotic", "bird", "reptile", "rabbit", "ferret", "rodent", "fish", "amphibian"],
        content_type="formulary",
        filename_patterns=[r"exotic.*animal.*formulary", r"carpenter.*exotic"],
        citation_format="Carpenter, J.W. Exotic Animal Formulary, 5th Ed. (2017). Elsevier.",
    ),

    "food_animal_surgery": BookMeta(
        key="food_animal_surgery",
        title="Food Animal Surgery",
        short_title="Food Animal Surgery (Noordsy)",
        authors=["Fubini, S.L.", "Ducharme, N.G."],
        edition="5th Edition",
        year="2017",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0470960554",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["surgery", "food animal", "bovine surgery", "large animal surgery"],
        species_tags=["bovine", "ovine", "caprine", "porcine"],
        content_type="textbook",
        filename_patterns=[r"food.*animal.*surg", r"noordsy", r"fubini.*ducharme"],
        citation_format="Fubini & Ducharme. Food Animal Surgery, 5th Ed. (2017). Wiley.",
    ),

    "equine_clinical_practice": BookMeta(
        key="equine_clinical_practice",
        title="Concise Textbook of Equine Clinical Practice",
        short_title="Equine Clinical Practice",
        authors=["Mair, T.", "Sherlock, C."],
        edition="1st Edition",
        year="2023",
        publisher="CRC Press / Taylor & Francis",
        publisher_short="CRC Press",
        isbn="978-1032268149",
        legal_status=PENDING,
        license_contact="permissions@taylorandfrancis.com",
        subject_tags=["equine", "clinical practice", "diagnosis", "treatment"],
        species_tags=["equine"],
        content_type="textbook",
        filename_patterns=[r"equine.*clinical.*pract", r"mair.*equine"],
        citation_format="Mair & Sherlock. Concise Textbook of Equine Clinical Practice (2023). CRC Press.",
    ),

    "camelid_medicine": BookMeta(
        key="camelid_medicine",
        title="Medicine and Surgery of Camelids",
        short_title="Medicine & Surgery of Camelids",
        authors=["Fowler, M.E."],
        edition="3rd Edition",
        year="2010",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-0813806167",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["camelid", "llama", "alpaca", "medicine", "surgery"],
        species_tags=["camelid", "llama", "alpaca", "camel"],
        content_type="textbook",
        filename_patterns=[r"camelid", r"fowler.*camel"],
        citation_format="Fowler, M.E. Medicine and Surgery of Camelids, 3rd Ed. (2010). Wiley.",
    ),

    # -------------------------------------------------------------------------
    # DIAGNOSTIC IMAGING
    # -------------------------------------------------------------------------

    "thralls_radiology": BookMeta(
        key="thralls_radiology",
        title="Textbook of Veterinary Diagnostic Radiology",
        short_title="Thrall's Radiology",
        authors=["Thrall, D.E."],
        edition="7th Edition",
        year="2018",
        publisher="Elsevier",
        publisher_short="Elsevier",
        isbn="978-0323482479",
        legal_status=PENDING,
        license_contact="healthpermissions@elsevier.com",
        subject_tags=["radiology", "diagnostic imaging", "X-ray", "radiograph"],
        species_tags=["dog", "cat", "bovine", "equine"],
        content_type="textbook",
        filename_patterns=[r"thrall.*radiol", r"vet.*diagnostic.*radiol"],
        citation_format="Thrall, D.E. Textbook of Veterinary Diagnostic Radiology, 7th Ed. (2018). Elsevier.",
    ),

    "small_animal_ultrasound": BookMeta(
        key="small_animal_ultrasound",
        title="Atlas of Small Animal Ultrasonography",
        short_title="Small Animal Ultrasonography",
        authors=["Penninck, D.", "d'Anjou, M.A."],
        edition="2nd Edition",
        year="2015",
        publisher="Wiley-Blackwell",
        publisher_short="Wiley",
        isbn="978-1118923573",
        legal_status=PENDING,
        license_contact="permissions@wiley.com",
        subject_tags=["ultrasonography", "ultrasound", "diagnostic imaging", "echocardiography"],
        species_tags=["dog", "cat"],
        content_type="atlas",
        filename_patterns=[r"small.*animal.*ultrasound", r"penninck.*ultrasound"],
        citation_format="Penninck & d'Anjou. Atlas of Small Animal Ultrasonography, 2nd Ed. (2015). Wiley.",
    ),

    "diagnostic_mri": BookMeta(
        key="diagnostic_mri",
        title="Diagnostic MRI in Dogs and Cats",
        short_title="Diagnostic MRI Dogs & Cats",
        authors=["Cherubini, G.B.", "Busoni, V."],
        edition="1st Edition",
        year="2020",
        publisher="CRC Press",
        publisher_short="CRC Press",
        isbn="978-1498799263",
        legal_status=PENDING,
        license_contact="permissions@taylorandfrancis.com",
        subject_tags=["MRI", "magnetic resonance imaging", "neuroimaging", "diagnostic imaging"],
        species_tags=["dog", "cat"],
        content_type="textbook",
        filename_patterns=[r"diagnostic.*mri", r"mri.*dogs.*cats", r"cherubini.*mri"],
        citation_format="Cherubini & Busoni. Diagnostic MRI in Dogs and Cats (2020). CRC Press.",
    ),

    # -------------------------------------------------------------------------
    # FIELD MANUALS & OPEN ACCESS
    # -------------------------------------------------------------------------

    "fao_livestock": BookMeta(
        key="fao_livestock",
        title="FAO Livestock Manuals",
        short_title="FAO Livestock Manuals",
        authors=["FAO"],
        edition="Various",
        year="2024",
        publisher="Food and Agriculture Organization of the United Nations",
        publisher_short="FAO",
        legal_status=OPEN_ACCESS,
        license_url="https://www.fao.org/open-access",
        subject_tags=["livestock", "animal health", "disease control", "husbandry"],
        species_tags=["bovine", "ovine", "caprine", "porcine", "poultry"],
        content_type="manual",
        filename_patterns=[r"fao.*livestock", r"fao.*animal"],
        citation_format="FAO. Livestock Manuals. Food and Agriculture Organization. [Open Access]",
    ),

    "oie_woah": BookMeta(
        key="oie_woah",
        title="OIE/WOAH Disease Manuals and Terrestrial/Aquatic Animal Health Codes",
        short_title="OIE/WOAH Disease Manuals",
        authors=["WOAH"],
        edition="Current",
        year="2024",
        publisher="World Organisation for Animal Health (WOAH/OIE)",
        publisher_short="WOAH",
        legal_status=OPEN_ACCESS,
        license_url="https://www.woah.org/en/what-we-do/standards/codes-and-manuals/",
        subject_tags=["notifiable diseases", "disease standards", "international health", "biosafety"],
        species_tags=["bovine", "equine", "ovine", "caprine", "porcine", "poultry", "aquatic"],
        content_type="manual",
        filename_patterns=[r"oie.*manual", r"woah.*manual", r"terrestrial.*code", r"aquatic.*code"],
        citation_format="WOAH. OIE Terrestrial/Aquatic Animal Health Code. World Organisation for Animal Health. [Open Access]",
    ),

    "extension_guides": BookMeta(
        key="extension_guides",
        title="Local Agricultural Extension Guides",
        short_title="Extension Guides",
        authors=["Various"],
        edition="Various",
        year="2024",
        publisher="Various — Government / NGO",
        publisher_short="Extension",
        legal_status=OPEN_ACCESS,
        subject_tags=["livestock", "husbandry", "local diseases", "field management"],
        species_tags=["bovine", "ovine", "caprine", "porcine", "poultry"],
        content_type="manual",
        filename_patterns=[r"extension.*guide", r"agric.*extension"],
        citation_format="Agricultural Extension Guide. [Public Domain / Open Access]",
    ),
}


# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def detect_book(filename: str) -> BookMeta | None:
    """
    Auto-detect which book a PDF is by matching filename patterns.

    Args:
        filename: The PDF filename (e.g. "fossum_small_animal_surgery_5e.pdf")

    Returns:
        Matching BookMeta or None if no match.

    Example:
        >>> detect_book("plumbs_drug_handbook_9th.pdf")
        BookMeta(key='plumbs', ...)
    """
    fn_lower = filename.lower()
    for book in BOOK_REGISTRY.values():
        for pattern in book.filename_patterns:
            if re.search(pattern, fn_lower):
                return book
    return None


def get_book_metadata(key: str, page_number: int = 1, chunk_index: int = 0) -> dict:
    """
    Get ChromaDB-ready metadata for a book by its registry key.

    Args:
        key:          Book registry key (e.g. "plumbs")
        page_number:  Page number for this chunk
        chunk_index:  Chunk index within the page

    Returns:
        dict suitable for ChromaDB metadata field.

    Raises:
        KeyError if the key doesn't exist in the registry.
    """
    book = BOOK_REGISTRY[key]
    return book.to_chroma_metadata(page_number=page_number, chunk_index=chunk_index)


def books_by_status(status: str) -> list[BookMeta]:
    """Return all books with a given legal status."""
    return [b for b in BOOK_REGISTRY.values() if b.legal_status == status]


def books_by_species(species: str) -> list[BookMeta]:
    """Return all books that cover a given species."""
    return [b for b in BOOK_REGISTRY.values() if species.lower() in b.species_tags]


def books_by_publisher(publisher_short: str) -> list[BookMeta]:
    """Return all books from a given publisher."""
    return [
        b for b in BOOK_REGISTRY.values()
        if b.publisher_short.lower() == publisher_short.lower()
    ]


def print_registry_summary():
    """Print a human-readable summary of the registry."""
    from rich.table import Table
    from rich.console import Console

    c = Console()
    table = Table(title=f"VetGPT Book Registry ({len(BOOK_REGISTRY)} titles)")
    table.add_column("Key", style="dim", width=28)
    table.add_column("Short Title", style="cyan", width=34)
    table.add_column("Publisher", width=12)
    table.add_column("Status", width=16)
    table.add_column("Species", width=30)

    status_colors = {
        OPEN_ACCESS: "[green]open_access[/green]",
        LICENSED:    "[cyan]licensed[/cyan]",
        PENDING:     "[yellow]pending[/yellow]",
        PERSONAL:    "[blue]personal[/blue]",
        RESTRICTED:  "[red]restricted[/red]",
    }

    for book in BOOK_REGISTRY.values():
        table.add_row(
            book.key,
            book.short_title,
            book.publisher_short,
            status_colors.get(book.legal_status, book.legal_status),
            ", ".join(book.species_tags[:4]),
        )

    c.print(table)

    # Summary by status
    for status in [OPEN_ACCESS, LICENSED, PENDING, PERSONAL, RESTRICTED]:
        count = len(books_by_status(status))
        if count:
            c.print(f"  {status_colors[status]}: {count} titles")
__all__ = [
    "BOOK_REGISTRY",
    "BookMeta",
    "OPEN_ACCESS",
    "PENDING_LICENSE",
    "detect_book",
    "books_by_species",
    "books_by_status",
    "print_registry_summary",
]

if __name__ == "__main__":
    print_registry_summary()
