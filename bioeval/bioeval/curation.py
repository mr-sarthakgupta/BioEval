"""Catalog-driven staging of granted data.

Grants are assembled from the hidden per-problem catalog only. Files are first
collected into a private temp directory (never visible to the UEA), passed through
the leak guard, and only the survivors are copied into the mounted grant directory.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from bioeval import providers
from bioeval.catalog import resolve_entry_files
from bioeval.guard import enforce
from bioeval.schemas import CatalogEntry, DataCatalog, DatasetGrant, DatasetRequest, GrantedFile

# Requests for the paper/code/solution itself are refused outright.
DENIED_RE = re.compile(
    r"\b(paper|manuscript|article|authors'? code|source code|github|repository|"
    r"\brepo\b|solution|answer key|ground truth|expected (?:result|conclusion)|doi)\b",
    re.IGNORECASE,
)
INVENTORY_REQUEST_RE = re.compile(
    r"\b(do you have|what (?:data|datasets)|which (?:data|datasets)|any datasets?|"
    r"all (?:data|datasets)|everything|anything related|available (?:data|datasets)|"
    r"datasets? on)\b",
    re.IGNORECASE,
)
PUBLIC_SOURCE_RE = re.compile(
    r"\b(accession|record|deposit|dataset|figshare|zenodo|dryad|geo|sra|arrayexpress|"
    r"bioproject|proteomexchange|empiar|supplementary data|source data|public source|"
    r"public repository|repository record)\b",
    re.IGNORECASE,
)
PUBLIC_IDENTIFIER_RE = re.compile(
    r"(https?://|10\.\d{4,9}/|GSE\d+|SR[APRSX]\d+|PRJ[DEN][A-Z]?\d+|PXD\d+|"
    r"E-[A-Z]+-\d+|\b\d{5,}\b)",
    re.IGNORECASE,
)
MEASUREMENT_RE = re.compile(
    r"\b(survival|lifespan|longevity|mortality|ageing|aging|physiology|activity|"
    r"locomotor|grip|weight|mass|expression|rna|sequence|genotype|phenotype|assay|"
    r"measurement|curve|time[- ]?series|count|rate|score|concentration|abundance|"
    r"binding|titration|kinetics?|occupancy|rotation|turnover|hydrolysis|dependency|"
    r"crispr|ic50|drug[- ]?response|sensitivity|perturbation|pathway|miscibility|"
    r"condensate|phase[- ]?separation|composition|phosphorylation|charge|aromatic|"
    r"serine)\b",
    re.IGNORECASE,
)
CONDITION_RE = re.compile(
    r"\b(treatment|treated|control|condition|diet|pollen|deprived|fed|dose|timepoint|"
    r"age|week|day|wild|field|captive|laboratory|insectary|environment|cohort|"
    r"comparison|versus|vs\.?|between|with|without|knockout|mutant|replicate|"
    r"atp|adp|nucleotide|cell[- ]?line|compound|drug|target|mutation|"
    r"phosphorylated|phosphomimetic)\b",
    re.IGNORECASE,
)
DATA_TYPE_RE = re.compile(
    r"\b(csv|tsv|xlsx|rds|table|matrix|records?|measurements?|curves?|raw reads?|"
    r"per[- ]individual|per[- ]sample|metadata|columns?|rows?|subset)\b",
    re.IGNORECASE,
)
COMMON_SCOPE_WORDS = {
    "adult",
    "age",
    "ageing",
    "aging",
    "and",
    "activity",
    "body",
    "butterfly",
    "butterflies",
    "curve",
    "curves",
    "species",
    "samples",
    "sample",
    "cells",
    "cell",
    "data",
    "dataset",
    "lifespan",
    "longevity",
    "mortality",
    "records",
    "measurements",
    "survival",
    "field",
    "for",
    "gut",
    "locomotor",
    "non",
    "or",
    "other",
    "score",
    "the",
    "weight",
    "with",
    "conditions",
    "adp",
    "atp",
    "assay",
    "bacterial",
    "binding",
    "cancer",
    "compound",
    "crispr",
    "csv",
    "construct",
    "constructs",
    "dna",
    "drug",
    "f1",
    "f1-atpase",
    "give",
    "ic50",
    "idr",
    "line",
    "measurements",
    "rna",
    "spreadsheet",
    "table",
    "tabular",
    "titration",
}
GENERIC_SCOPE_RE = re.compile(
    r"\b(related|multiple|various|several|sampled|neotropical|mammalian|human|mouse|"
    r"butterfly|butterflies|species|organisms?|samples?)\b",
    re.IGNORECASE,
)
BINOMIAL_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+|\s*[._]\s*)[a-z][a-z-]{2,}\b")
ABBREVIATED_SPECIES_RE = re.compile(r"\b[A-Z]\.\s*[a-z][a-z-]{2,}\b")
NAMED_COHORT_RE = re.compile(
    r"\b(cohort|strain|cell line|clone|isolate|population|individuals?|samples?)\s+"
    r"[\w.-]+",
    re.IGNORECASE,
)
COMPARISON_RE = re.compile(r"\b(vs\.?|versus|compared (?:with|to)|between)\b", re.IGNORECASE)
SPECIES_ABBREV_RE = re.compile(r"\b([A-Z])\.\s*([a-z][a-z-]{2,})\b")
PROTEIN_OR_CONSTRUCT_RE = re.compile(r"\b(?:F1[- ]?ATPase|[A-Z0-9]{2,}(?:[-_][A-Za-z0-9]+)+)\b")
MEASUREMENT_FAMILIES: dict[str, set[str]] = {
    "survival": {
        "survival", "lifespan", "longevity", "mortality", "age at death",
        "age-at-death", "days survived", "survival curve", "censoring", "hazard",
        "gompertz", "weibull", "mark-recapture", "recapture",
    },
    "locomotor": {"locomotor", "activity", "distance traveled", "distance travelled"},
    "weight": {"weight", "body weight", "body mass", "mass"},
    "gut_score": {"gut score", "gut condition", "max_gs", "gs"},
    "phylogeny": {"phylogeny", "phylogenetic", "tree", "newick"},
    "metadata": {"metadata", "sample metadata", "supplementary", "forewing", "wing length"},
    "oxidative_stress": {
        "oxidative", "oxidative stress", "lipid peroxidation", "mda", "tbars",
        "protein carbonylation", "protein carbonyl", "carbonylation", "catalase",
        "superoxide dismutase", "sod", "glutathione", "antioxidant", "ros",
    },
    "immune": {"immune", "hemocyte", "phenoloxidase", "encapsulation"},
    "fecundity": {"fecundity", "egg", "egg production", "reproductive output"},
    "toxin": {"toxin", "toxicity", "cyanogenic", "chemical defense", "chemical defence"},
    "metabolic": {"metabolic", "metabolism", "metabolic rate", "respiration"},
    "binding_kinetics": {
        "binding", "titration", "nucleotide", "atp", "adp", "mixed nucleotide",
        "kinetic", "kinetics", "turnover", "hydrolysis", "occupancy",
    },
    "rotation": {"rotation", "rotary", "gamma-subunit", "single-molecule", "step"},
    "dependency": {"dependency", "gene dependency", "loss-of-function", "crispr"},
    "expression": {"expression", "gene expression", "rna", "transcriptomic", "transcriptome"},
    "drug_response": {"drug response", "drug sensitivity", "ic50", "compound sensitivity"},
    "pathway_features": {"pathway", "pathway-enrichment", "pathway enrichment", "feature"},
    "miscibility": {"miscibility", "immiscibility", "mixing", "demixing", "condensate"},
    "sequence_composition": {
        "sequence", "amino acid", "composition", "serine", "aromatic", "charge",
        "charged residues", "phosphorylation",
    },
}
UNAVAILABLE_FAMILIES = {"oxidative_stress", "immune", "fecundity", "toxin", "metabolic"}


@dataclass
class StageInstruction:
    entry_id: str
    rows: int | None = None
    columns: list[str] | None = None
    use_online: bool = False


@dataclass
class GrantPlan:
    instructions: list[StageInstruction] = field(default_factory=list)
    message: str = ""
    deny: bool = False
    deny_reason: str | None = None


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower())}


def is_inventory_request(question: str) -> bool:
    """Return True for broad catalog-discovery requests that should be clarified."""
    if not INVENTORY_REQUEST_RE.search(question):
        return False

    # "Do you have X measurements for Y under Z?" is phrased as a question, but
    # it is not catalog discovery. Treat inventory language as broad only when the
    # request lacks enough concrete scientific scope for a grant decision.
    text = question.strip()
    has_measurement = bool(MEASUREMENT_RE.search(text))
    has_scope = _has_specific_scope(text)
    has_context = bool(CONDITION_RE.search(text) or DATA_TYPE_RE.search(text))
    asks_experiment = bool(re.search(r"\b(experiment|assay|measure|test|derive|generate|compare)\b", text, re.I))
    return not (has_measurement and has_scope and (has_context or asks_experiment))


def is_public_source_request(question: str) -> bool:
    return bool(PUBLIC_SOURCE_RE.search(question) and PUBLIC_IDENTIFIER_RE.search(question))


def _has_specific_scope(question: str) -> bool:
    if ABBREVIATED_SPECIES_RE.search(question) or NAMED_COHORT_RE.search(question):
        return True
    if PROTEIN_OR_CONSTRUCT_RE.search(question):
        return True
    for match in BINOMIAL_RE.finditer(question):
        parts = re.split(r"\s+|[._]\s*", match.group(0).strip())
        if (
            len(parts) >= 2
            and parts[0].lower() not in COMMON_SCOPE_WORDS
            and parts[1].lower() not in COMMON_SCOPE_WORDS
        ):
            return True
    for match in re.finditer(r"\b[A-Z][A-Z0-9]{1,}(?:[-_][A-Z0-9]+)*\b", question):
        token = match.group(0).lower()
        if token not in COMMON_SCOPE_WORDS:
            return True
    return False


def specificity_issue(request: DatasetRequest) -> str | None:
    """Return a clarification reason if the data request is too broad to grant."""
    if os.getenv("BIOEVAL_STRICT_DATA_REQUESTS", "1").lower() in {"0", "false", "off", "none"}:
        return None

    question = request.question.strip()
    if is_inventory_request(question):
        return clarification_message()
    if is_public_source_request(question):
        return None

    text = " ".join([question, *request.desired_modalities])
    has_measurement = bool(MEASUREMENT_RE.search(text) or request.desired_modalities)
    has_scope = _has_specific_scope(question)
    has_context = bool(CONDITION_RE.search(text) or DATA_TYPE_RE.search(text))
    asks_experiment = bool(re.search(r"\b(experiment|assay|measure|test|derive|generate|compare)\b", text, re.I))

    if not has_measurement:
        return (
            "Please name the concrete measurement or data type you need, plus the exact "
            "species/sample/cohort and condition or experiment."
        )
    if not has_scope:
        return (
            "Please make the biological scope more specific: name the species, cohort, "
            "sample/accession, comparison, or exact public dataset. Broad genus/topic "
            "requests are not grantable."
        )
    if not has_context and not asks_experiment:
        return (
            "Please specify the condition, treatment, environment, timepoint, comparison, "
            "requested columns/rows, or concrete experiment that would produce the data."
        )
    return None


def clarification_message() -> str:
    return (
        "Please make a specific data request: name one concrete dataset or one concrete "
        "experiment, including the measurement/data type, exact species/sample/cohort or "
        "accession, condition/treatment/environment, and desired scope. I cannot answer "
        "broad inventory requests or dump related datasets."
    )


def generic_denial_message() -> str:
    return (
        "No exact grantable dataset matched this request, or the request is not specific "
        "enough. Please ask for one concrete measurement from one named species/cohort, "
        "treatment/condition, and experiment or public source."
    )


def generic_partial_message(file_count: int) -> str:
    noun = "file" if file_count == 1 else "files"
    return f"Granted {file_count} exact-match {noun}; unrelated data were withheld."


def select_instructions_by_keywords(catalog: DataCatalog, request: DatasetRequest) -> list[StageInstruction]:
    """Deterministic fallback selection when no LLM/opencode planner is available."""
    if is_inventory_request(request.question):
        return []
    req_tokens = _tokens(" ".join([request.question, *request.desired_modalities]))
    scored: list[tuple[int, CatalogEntry]] = []
    for entry in catalog.grantable():
        hay = _tokens(" ".join([entry.id, entry.description, *entry.modalities]))
        score = len(req_tokens & hay)
        scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)

    # The deterministic fallback prefers local data and never triggers a surprise
    # network fetch; online entries are a deliberate LLM/agent choice.
    local = [(s, e) for s, e in scored if e.source_paths]
    top = [e for s, e in local if s > 0][:1]
    if not top:
        top = [e for _, e in local][:1]
    if not top:
        # No local data at all (e.g. a pure modeling problem): surface the catalog's
        # online/literature guidance entries without auto-downloading.
        top = [e for _, e in scored if e.online is None][:1]
        return [StageInstruction(entry_id=e.id, use_online=False) for e in top]
    return [StageInstruction(entry_id=e.id) for e in top]


def _max_grants_per_request() -> int:
    raw = os.getenv("BIOEVAL_MAX_DATASET_GRANTS_PER_REQUEST", "1").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 1


def _measurement_families_in_text(text: str) -> set[str]:
    low = text.lower()
    families: set[str] = set()
    for family, terms in MEASUREMENT_FAMILIES.items():
        if any(term in low for term in terms):
            families.add(family)
    return families


def _entry_measurement_families(entry: CatalogEntry) -> set[str]:
    return _measurement_families_in_text(
        " ".join([entry.id, entry.description, *entry.modalities])
    )


def measurement_issue(request: DatasetRequest, entry: CatalogEntry) -> str | None:
    if os.getenv("BIOEVAL_STRICT_DATA_REQUESTS", "1").lower() in {"0", "false", "off", "none"}:
        return None
    requested = _measurement_families_in_text(
        " ".join([request.question, *request.desired_modalities])
    )
    if requested & UNAVAILABLE_FAMILIES:
        # These families must be explicitly represented in the catalog entry. A species
        # row subset from survival/weight data is not an exact match for biochemical or
        # reproductive assays.
        entry_families = _entry_measurement_families(entry)
        if not requested & entry_families:
            return generic_denial_message()
    precise_requested = requested - {"metadata"}
    if precise_requested:
        entry_families = _entry_measurement_families(entry)
        if not precise_requested & entry_families:
            return generic_denial_message()
    return None


def _request_species_terms(question: str) -> set[str]:
    terms: set[str] = set()
    for match in BINOMIAL_RE.finditer(question):
        parts = [p for p in re.split(r"\s+|[._]\s*", match.group(0).strip()) if p]
        if (
            len(parts) >= 2
            and parts[0].lower() not in COMMON_SCOPE_WORDS
            and parts[1].lower() not in COMMON_SCOPE_WORDS
        ):
            genus = parts[0].lower()
            epithet = parts[1].lower()
            terms.update({genus, epithet, f"{genus} {epithet}", f"{genus[0]}_{epithet}", f"{genus[0]}. {epithet}"})
    for genus_initial, epithet in SPECIES_ABBREV_RE.findall(question):
        epithet = epithet.lower()
        terms.update({epithet, f"{genus_initial.lower()}_{epithet}", f"{genus_initial.lower()}. {epithet}"})
    return terms


def _request_treatment_terms(question: str) -> set[str]:
    low = question.lower()
    terms: set[str] = set()
    if re.search(r"\bpollen[- ]?fed\b|\bwith pollen\b|\bpollen access\b", low):
        terms.update({"pf", "pollen-fed", "pollen fed"})
    if re.search(r"\bpollen[- ]?deprived\b|\bsugar[- ]?only\b|\bwithout pollen\b|\bno pollen\b", low):
        terms.update({"pd", "pollen-deprived", "pollen deprived", "sugar-only", "sugar only"})
    if "amino acid" in low or "amino-acid" in low:
        terms.update({"amino", "amino acid", "amino-acid"})
    return terms


def _request_named_terms(question: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", question):
        normalized = token.lower().strip("_-")
        if normalized and normalized not in COMMON_SCOPE_WORDS:
            terms.add(normalized)
        for part in re.split(r"[-_]", normalized):
            if len(part) >= 3 and part not in COMMON_SCOPE_WORDS:
                terms.add(part)
    return terms


def _series_contains_any(series, terms: set[str]):
    values = series.astype(str).str.lower()
    mask = values.apply(lambda value: any(term in value for term in terms))
    return mask


def _derive_rds_subset_for_request(
    src: Path,
    dest: Path,
    request: DatasetRequest,
    notes: list[str],
) -> str:
    """Derive a CSV row subset from an RDS data frame.

    Returns: "derived", "no_match", or "not_applicable".
    """
    if src.suffix.lower() not in {".rds"}:
        return "not_applicable"
    species_terms = _request_species_terms(request.question)
    treatment_terms = _request_treatment_terms(request.question)
    if not species_terms and not treatment_terms:
        return "not_applicable"
    try:
        import pyreadr  # noqa: PLC0415
    except Exception:
        notes.append("Could not derive an exact RDS subset because pyreadr is unavailable.")
        return "no_match"
    try:
        result = pyreadr.read_r(str(src))
    except Exception:
        return "no_match"
    if not result:
        return "no_match"
    import pandas as pd  # noqa: PLC0415

    df = next((value for value in result.values() if isinstance(value, pd.DataFrame)), None)
    if df is None or df.empty:
        return "no_match"

    mask = pd.Series(True, index=df.index)
    applied_filter = False
    species_cols = [
        col for col in df.columns
        if any(key in str(col).lower() for key in ["species", "genus", "taxon"])
    ]
    if species_terms and species_cols:
        species_mask = pd.Series(False, index=df.index)
        for col in species_cols:
            species_mask |= _series_contains_any(df[col], species_terms)
        mask &= species_mask
        applied_filter = True
    elif species_terms:
        return "no_match"

    treatment_cols = [
        col for col in df.columns
        if any(key in str(col).lower() for key in ["diet", "treatment", "condition", "group"])
    ]
    if treatment_terms:
        if not treatment_cols:
            return "no_match"
        treatment_mask = pd.Series(False, index=df.index)
        for col in treatment_cols:
            treatment_mask |= _series_contains_any(df[col], treatment_terms)
        mask &= treatment_mask
        applied_filter = True

    if not applied_filter:
        return "not_applicable"
    subset = df.loc[mask]
    if subset.empty:
        return "no_match"
    out = dest.with_suffix(".csv")
    subset.to_csv(out, index=False)
    notes.append(
        f"Derived an exact row subset for '{out.parent.name}/{out.name}' "
        f"from {len(subset)} of {len(df)} rows."
    )
    return "derived"


def _filename_relevant_to_request(src: Path, request: DatasetRequest) -> bool:
    species_terms = _request_species_terms(request.question)
    treatment_terms = _request_treatment_terms(request.question)
    if not species_terms and not treatment_terms:
        return True
    name = src.name.lower()
    normalized_name = name.replace(".", "_").replace("-", "_")
    species_match = not species_terms or any(
        term.replace(" ", "_").replace(".", "_").replace("-", "_") in normalized_name
        or term in name
        for term in species_terms
    )
    treatment_match = not treatment_terms or any(
        term.replace(" ", "_").replace(".", "_").replace("-", "_") in normalized_name
        or term in name
        for term in treatment_terms
    )
    # Generic data-frame names may still be subsettable by content, so do not reject
    # them here; the RDS subsetter gets the first chance above.
    generic_name = name in {
        "lifespan_data.rds",
        "longsurv.rds",
        "totalcogsurv.rds",
        "table_1_data.rds",
        "iddata.rds",
        "sightings.rds",
        "locomotordata.rds",
        "fullgsdata.rds",
        "fullweightdata2.rds",
    }
    return generic_name or (species_match and treatment_match)


def _derive_table(src: Path, dest: Path, rows: int | None, columns: list[str] | None) -> bool:
    """Write a row/column subset of a CSV/TSV/parquet. Returns True on success."""
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:
        return False
    suffix = src.suffix.lower()
    try:
        if suffix in {".csv", ".tsv", ".txt"}:
            sep = "\t" if suffix == ".tsv" else ","
            df = pd.read_csv(src, sep=sep, nrows=rows, usecols=columns)
            dest = dest.with_suffix(".csv")
            df.to_csv(dest, index=False)
        elif suffix == ".parquet":
            df = pd.read_parquet(src, columns=columns)
            if rows:
                df = df.head(rows)
            df.to_parquet(dest)
        else:
            return False
    except Exception:
        return False
    return True


def _derive_tabular_subset_for_request(
    src: Path,
    dest: Path,
    request: DatasetRequest,
    notes: list[str],
) -> str:
    """Derive a content-based subset from tabular files using named request terms.

    Returns: "derived", "no_match", or "not_applicable".
    """
    suffix = src.suffix.lower()
    if suffix not in {".csv", ".tsv", ".txt", ".parquet"}:
        return "not_applicable"
    terms = _request_named_terms(request.question)
    if not terms:
        return "not_applicable"
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:
        return "not_applicable"

    try:
        if suffix == ".parquet":
            columns = list(pd.read_parquet(src, columns=[]).columns)
        else:
            sep = "\t" if suffix == ".tsv" else ","
            columns = list(pd.read_csv(src, sep=sep, nrows=0).columns)
    except Exception:
        return "not_applicable"

    normalized_columns = {str(col).lower(): col for col in columns}
    matched_columns = [
        col for low, col in normalized_columns.items()
        if any(term == low or term in low for term in terms)
    ]
    row_id_columns = [
        col for col in columns[:3]
        if any(key in str(col).lower() for key in ["cell", "sample", "drug", "compound", "construct", "protein", "idr", "name"])
    ]
    use_columns = list(dict.fromkeys([*row_id_columns, *matched_columns]))
    if not use_columns and src.stat().st_size < 5_000_000:
        return "not_applicable"
    if not use_columns:
        return "no_match"

    try:
        if suffix == ".parquet":
            df = pd.read_parquet(src, columns=use_columns)
        else:
            df = pd.read_csv(src, sep=sep, usecols=use_columns)
    except Exception:
        return "not_applicable"

    row_mask = None
    for col in row_id_columns:
        if col in df.columns:
            col_mask = _series_contains_any(df[col], terms)
            row_mask = col_mask if row_mask is None else (row_mask | col_mask)
    if row_mask is not None and row_mask.any() and not matched_columns and src.stat().st_size < 50_000_000:
        try:
            if suffix == ".parquet":
                df = pd.read_parquet(src)
            else:
                df = pd.read_csv(src, sep=sep)
            row_mask = None
            for col in row_id_columns:
                if col in df.columns:
                    col_mask = _series_contains_any(df[col], terms)
                    row_mask = col_mask if row_mask is None else (row_mask | col_mask)
        except Exception:
            pass
    if row_mask is not None and row_mask.any():
        df = df.loc[row_mask]

    # If only identifier columns matched but no row matched, this file is not an
    # exact content match for the named request.
    if not matched_columns and (row_mask is None or not row_mask.any()):
        return "no_match" if src.stat().st_size >= 5_000_000 else "not_applicable"
    if df.empty:
        return "no_match"

    out = dest.with_suffix(".parquet" if suffix == ".parquet" else ".csv")
    if suffix == ".parquet":
        df.to_parquet(out, index=False)
    else:
        df.to_csv(out, index=False)
    notes.append(
        f"Derived an exact table subset for '{out.parent.name}/{out.name}' "
        f"using named rows/columns from the request."
    )
    return "derived"


def _xlsx_relevant_to_request(src: Path, request: DatasetRequest) -> bool:
    if src.suffix.lower() != ".xlsx":
        return True
    terms = _request_named_terms(request.question)
    if not terms:
        return True
    try:
        text_parts: list[str] = []
        with zipfile.ZipFile(src) as archive:
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                if not (name.startswith("xl/sharedStrings") or name.startswith("xl/worksheets/")):
                    continue
                text_parts.append(archive.read(name).decode("utf-8", "ignore").lower())
        text = "\n".join(text_parts)
    except Exception:
        return True
    return any(term in text for term in terms)


def _neutral_file_name(index: int, src: Path) -> str:
    suffix = src.suffix.lower()
    return f"file_{index:03d}{suffix or '.dat'}"


def _stage_local_entry(
    entry: CatalogEntry,
    problem_root: Path,
    stage_dir: Path,
    instr: StageInstruction,
    *,
    public_entry_id: str,
    remaining_bytes: int,
    notes: list[str],
    request: DatasetRequest,
) -> int:
    staged = 0
    for file_index, src in enumerate(resolve_entry_files(problem_root, entry), start=1):
        neutral_name = _neutral_file_name(file_index, src)
        dest = stage_dir / public_entry_id / neutral_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = src.stat().st_size
        if os.getenv("BIOEVAL_STRICT_DATA_REQUESTS", "1").lower() not in {"0", "false", "off", "none"}:
            subset_status = _derive_rds_subset_for_request(src, dest, request, notes)
            if subset_status == "derived":
                staged += dest.with_suffix(".csv").stat().st_size
                continue
            if subset_status == "no_match":
                notes.append(
                    f"Skipped '{public_entry_id}/{neutral_name}' because it did not contain "
                    "rows matching the requested species/treatment scope."
                )
                continue
            if not _filename_relevant_to_request(src, request):
                notes.append(
                    f"Skipped '{public_entry_id}/{neutral_name}' because the file name did not "
                    "match the requested species/treatment scope."
                )
                continue
            tabular_subset_status = _derive_tabular_subset_for_request(src, dest, request, notes)
            if tabular_subset_status == "derived":
                staged += dest.with_suffix(".parquet" if src.suffix.lower() == ".parquet" else ".csv").stat().st_size
                continue
            if tabular_subset_status == "no_match":
                notes.append(
                    f"Skipped '{public_entry_id}/{neutral_name}' because it did not contain "
                    "rows or columns matching the named request scope."
                )
                continue
            if not _xlsx_relevant_to_request(src, request):
                notes.append(
                    f"Skipped '{public_entry_id}/{neutral_name}' because the spreadsheet content "
                    "did not match the named request scope."
                )
                continue
        wants_subset = instr.rows is not None or instr.columns is not None
        if wants_subset and _derive_table(src, dest, instr.rows, instr.columns):
            staged += dest.stat().st_size if dest.exists() else 0
            notes.append(f"Derived a requested table subset for '{public_entry_id}/{neutral_name}'.")
            continue
        if size > remaining_bytes - staged:
            notes.append(
                f"Skipped '{public_entry_id}/{neutral_name}' ({size} bytes) to stay within the "
                f"{remaining_bytes} byte budget; ask for a subset (rows/columns)."
            )
            continue
        shutil.copy2(src, dest)
        staged += size
    return staged


def _stage_online_entry(
    entry: CatalogEntry,
    stage_dir: Path,
    *,
    public_entry_id: str,
    per_file_bytes: int,
    remaining_bytes: int,
    notes: list[str],
) -> int:
    if not entry.online:
        notes.append(
            f"No direct download is configured for '{public_entry_id}'. {entry.description.strip()}"
        )
        return 0
    dest = stage_dir / public_entry_id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        fetched = providers.fetch_online_spec(
            entry.online,
            dest,
            max_bytes=per_file_bytes,
            max_total_bytes=remaining_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - report fetch failures, do not crash
        notes.append(f"Online fetch for '{public_entry_id}' failed: {exc}")
        return 0
    return sum(f.bytes for f in fetched)


def stage_and_grant(
    *,
    problem_root: Path,
    catalog: DataCatalog,
    identifiers: list[str],
    staging_root: Path,
    sandbox_data_root: str,
    request: DatasetRequest,
    request_id: str,
    plan: GrantPlan,
) -> DatasetGrant:
    if plan.deny or DENIED_RE.search(request.question):
        reason = "planner_denied" if plan.deny else "restricted_request_terms"
        return DatasetGrant(
            request_id=request_id,
            status="denied",
            message=generic_denial_message(),
            denial_reason=reason,
        )
    issue = specificity_issue(request)
    if issue:
        return DatasetGrant(
            request_id=request_id,
            status="denied",
            message=issue,
            denial_reason=f"specificity_issue: {issue}",
        )

    notes: list[str] = []
    tmp_root = Path(tempfile.mkdtemp(prefix=f"bioeval_stage_{request_id}_"))
    try:
        remaining = request.max_bytes
        grant_limit = _max_grants_per_request()
        explicit_public_source = is_public_source_request(request.question)
        selected_instructions = plan.instructions
        if len(selected_instructions) > grant_limit:
            notes.append(
                f"Narrowed an over-broad grant plan from {len(selected_instructions)} "
                f"dataset(s) to the first {grant_limit} exact-match candidate(s)."
            )
            selected_instructions = selected_instructions[:grant_limit]
        for instr in selected_instructions:
            entry = catalog.by_id_or_public_id(instr.entry_id)
            if entry is None:
                notes.append(f"Unknown requested dataset id '{instr.entry_id}'.")
                continue
            public_entry_id = catalog.public_id_for(entry.id) or "dataset_unknown"
            if not entry.grantable:
                notes.append(f"'{instr.entry_id}' is not grantable.")
                continue
            measure_issue = measurement_issue(request, entry)
            if measure_issue:
                notes.append("Skipped a candidate because its measurement type did not exactly match the request.")
                continue
            if remaining <= 0:
                notes.append("Reached the byte budget; request a subset for more.")
                break
            if (instr.use_online or not entry.source_paths or entry.kind == "online") and not explicit_public_source:
                notes.append(
                    "Skipped an online/public-deposit candidate because such data must be "
                    "requested by a specific source, accession, or repository record."
                )
                continue
            if instr.use_online or not entry.source_paths:
                used = _stage_online_entry(
                    entry,
                    tmp_root,
                    public_entry_id=public_entry_id,
                    per_file_bytes=request.max_bytes,
                    remaining_bytes=remaining,
                    notes=notes,
                )
            else:
                used = _stage_local_entry(
                    entry,
                    problem_root,
                    tmp_root,
                    instr,
                    public_entry_id=public_entry_id,
                    remaining_bytes=remaining,
                    notes=notes,
                    request=request,
                )
            remaining -= used

        report = enforce(tmp_root, identifiers)

        grant_dir = staging_root / request_id
        grant_dir.mkdir(parents=True, exist_ok=True)
        granted_files: list[GrantedFile] = []
        final_counts: dict[str, int] = {}
        for src in report.kept:
            staged_rel = src.relative_to(tmp_root)
            dataset_dir = (
                staged_rel.parts[0]
                if staged_rel.parts and re.fullmatch(r"dataset_\d{3}", staged_rel.parts[0])
                else "dataset_000"
            )
            final_counts[dataset_dir] = final_counts.get(dataset_dir, 0) + 1
            rel = Path(dataset_dir) / _neutral_file_name(final_counts[dataset_dir], src)
            dest = grant_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            granted_files.append(
                GrantedFile(
                    source_path=str(rel),
                    sandbox_path=f"{sandbox_data_root.rstrip('/')}/{request_id}/{rel}",
                    bytes=dest.stat().st_size,
                    reason="Matched the request and cleared the leak guard.",
                )
            )

        rejected_notes = [f"{rel}: {reason}" for rel, reason in report.rejected]
        if rejected_notes:
            notes.append(
                f"Withheld {len(rejected_notes)} item(s) that resembled code, models, "
                "documents, or paper identifiers."
            )

        status = "granted" if granted_files else "denied"
        if granted_files and (notes or rejected_notes):
            status = "partial"

        message = (
            generic_partial_message(len(granted_files))
            if granted_files and notes
            else "Placed the requested exact-match data into the sandbox data directory."
            if granted_files
            else generic_denial_message()
        )

        grant = DatasetGrant(
            request_id=request_id,
            status=status,
            message=message,
            denial_reason=(
                "no_files_survived_staging"
                if not granted_files and notes
                else "no_exact_grantable_match"
                if not granted_files
                else None
            ),
            files=granted_files,
            rejected=rejected_notes,
            manifest_path=(
                f"{sandbox_data_root.rstrip('/')}/{request_id}/DATA_GRANT_MANIFEST.json"
                if granted_files
                else None
            ),
        )
        if granted_files:
            (grant_dir / "DATA_GRANT_MANIFEST.json").write_text(
                json.dumps(grant.model_dump(), indent=2)
            )
        return grant
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
