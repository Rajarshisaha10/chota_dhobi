from bs4 import BeautifulSoup


def _normalize_label(label):
    if not label:
        return ""
    cleaned = (
        label.replace("\xa0", " ")
        .replace(":", " ")
        .replace("-", " ")
        .replace("/", " ")
        .replace(".", " ")
    )
    cleaned = " ".join(cleaned.split()).strip().lower()
    return cleaned


def _extract_tables(soup):
    tables = []
    for table in soup.find_all("table"):
        pairs = []
        labels_norm = set()
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(" ", strip=True)
            value = cells[1].get_text(" ", strip=True)
            if label and value:
                pairs.append((label, value))
                labels_norm.add(_normalize_label(label))
        if pairs:
            tables.append({"pairs": pairs, "labels_norm": labels_norm})
    return tables


def _find_first_value(pairs, label_keys):
    for label, value in pairs:
        if _normalize_label(label) in label_keys:
            return value
    return None


def parse_profile(html_content):
    """
    Parses the VTOP Student Profile HTML response into a dictionary.

    Returns:
        {
          "personal": {"name": "...", "reg_no": "...", "mobile": "..."},
          "educational": {"reg_no": "..."},
          "hostel": {"room": "...", "hostel": "...", "block": "..."}
        }
    """
    if not html_content:
        return {}

    soup = BeautifulSoup(html_content, "html.parser")
    tables = _extract_tables(soup)
    if not tables:
        return {}

    pairs = []
    for table in tables:
        pairs.extend(table["pairs"])
    if not pairs:
        return {}

    flat = {}
    for label, value in pairs:
        key = _normalize_label(label)
        if key and key not in flat:
            flat[key] = value

    personal = {}
    educational = {}
    hostel = {}

    student_name = None
    student_name_keys = {
        "student name",
        "name of student",
        "student s name",
    }
    name_keys = {"name"}
    reg_keys = {
        "reg no",
        "regno",
        "reg number",
        "registration no",
        "registration number",
        "register no",
    }

    for table in tables:
        candidate = _find_first_value(table["pairs"], student_name_keys)
        if candidate:
            student_name = candidate
            break

    if not student_name:
        for table in tables:
            if "name" in table["labels_norm"] and table["labels_norm"].intersection(reg_keys):
                candidate = _find_first_value(table["pairs"], name_keys)
                if candidate:
                    student_name = candidate
                    break

    if not student_name:
        student_name = _find_first_value(pairs, name_keys)

    if student_name:
        personal["name"] = student_name

    for key, value in flat.items():
        if key in {
            "reg no",
            "regno",
            "reg number",
            "registration no",
            "registration number",
            "register no",
        }:
            educational["reg_no"] = value
        elif key in {"mobile", "mobile no", "mobile number", "phone", "phone no"}:
            personal["mobile"] = value
        elif key in {"room", "room no", "room number"}:
            hostel["room"] = value
        elif key in {"hostel", "hostel name"}:
            hostel["hostel"] = value
        elif key in {"block"}:
            hostel["block"] = value

    if not (personal or educational or hostel):
        return {}

    return {
        "personal": personal,
        "educational": educational,
        "hostel": hostel,
    }
