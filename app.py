"""RP1 MCQ Validation Portal.

This is a clean implementation of the study protocol.  The question bank is
read only from ``mcq_repository.csv``; validation submissions are append-only.
"""

from __future__ import annotations

import csv
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).parent
QUESTION_FILE = APP_DIR / "mcq_repository.csv"
BACKUP_FILE = APP_DIR / "validations_backup.csv"

# Deliberately enumerate only fields safe for the teacher workflow.  The CSV's
# private researcher-review field is never loaded.
QUESTION_COLUMNS = [
    "ID", "Topic", "Question Type", "Bloom", "Question", "A", "B", "C", "D",
    "Answer", "Explanation",
]
SHEET_COLUMNS = [
    "timestamp", "question_id", "topic", "bloom", "decision", "school",
    "question_type", "teacher_answer", "answer_key", "answer_agreement",
    "validator_id", "validator_name", "technical_accuracy", "clarity",
    "bloom_alignment", "distractor_quality", "curriculum_fit",
    "overall_suitability", "reason_codes", "comments",
]
RATING_FIELDS = [
    ("technical_accuracy", "Technical Accuracy"),
    ("bloom_alignment", "Bloom Alignment"),
    ("clarity", "Clarity"),
    ("distractor_quality", "Distractor Quality"),
    ("curriculum_fit", "Curriculum Fit"),
    ("overall_suitability", "Overall Suitability"),
]
RATING_LABELS = {
    "1": "Major problem",
    "2": "Significant concern",
    "3": "Acceptable",
    "4": "Good",
    "5": "Excellent",
}
REASON_CODES = [
    "WRONG_KEY", "EXPLANATION_ERROR", "BLOOM_MISMATCH", "CLARITY", "DISTRACTOR",
    "CURRICULUM", "MULTIPLE_VALID_ANSWERS", "DIFFICULTY", "OTHER",
]
CODE_PATTERN = re.compile(r"\{\{CODE\}\}(.*?)\{\{/CODE\}\}", re.DOTALL)


def widget_key(field: str, question_id: str) -> str:
    return f"{field}_{question_id}"


def reset_question_form(question_id: str) -> None:
    """Remove all unsaved state for a question before navigating into it."""
    fields = ["stage", "teacher_answer", "committed_answer", "decision", "reason_codes", "comments"]
    fields.extend(field for field, _ in RATING_FIELDS)
    for field in fields:
        st.session_state.pop(widget_key(field, question_id), None)


def navigate_to(question_id: str, submitted_ids: set[str]) -> None:
    if question_id not in submitted_ids:
        reset_question_form(question_id)
    st.session_state.current_question_id = question_id


@st.cache_data(show_spinner=False)
def load_questions(file_stamp: float) -> pd.DataFrame:
    del file_stamp
    questions = pd.read_csv(QUESTION_FILE, usecols=QUESTION_COLUMNS, dtype=str).fillna("")
    missing = set(QUESTION_COLUMNS) - set(questions.columns)
    if missing:
        raise ValueError(f"Question file is missing: {', '.join(sorted(missing))}")
    if questions["ID"].duplicated().any():
        raise ValueError("Every question ID must be unique.")
    return questions


def get_questions() -> pd.DataFrame:
    if not QUESTION_FILE.exists():
        st.error("Add mcq_repository.csv beside app.py before starting the portal.")
        st.stop()
    return load_questions(QUESTION_FILE.stat().st_mtime)


def render_text_with_code(value: str) -> None:
    """Render normal text and marked Python snippets without altering content."""
    cursor = 0
    for match in CODE_PATTERN.finditer(value):
        before = value[cursor:match.start()]
        if before.strip():
            st.markdown(html.escape(before).replace("\n", "  \n"))
        st.code(match.group(1).replace("\\n", "\n").strip("\n"), language="python")
        cursor = match.end()
    after = value[cursor:]
    if after.strip():
        st.markdown(html.escape(after).replace("\n", "  \n"))


def has_code(value: str) -> bool:
    return bool(CODE_PATTERN.search(value))


def option_label(option: tuple[str, str]) -> str:
    """Keep each full option within its radio choice, including code text."""
    letter, content = option
    plain_content = content.replace("{{CODE}}", "").replace("{{/CODE}}", "").replace("\\n", " ")
    return f"{letter}. " + plain_content


def render_question(question: pd.Series) -> None:
    metadata = (
        f"<span>Topic: {html.escape(question['Topic'])}</span>"
        f"<span>Question Type: {html.escape(question['Question Type'])}</span>"
        f"<span>Target Bloom Level: {html.escape(question['Bloom'])}</span>"
    )
    st.markdown(f'<div class="question-metadata">{metadata}</div>', unsafe_allow_html=True)
    if has_code(question["Question"]):
        render_text_with_code(question["Question"])
    else:
        st.markdown(f'<div class="question-prompt">{html.escape(question["Question"])}</div>', unsafe_allow_html=True)


def render_options(question: pd.Series) -> None:
    """Keep the choices visible when the teacher is rating an item."""
    for letter in "ABCD":
        option = question[letter]
        if has_code(option):
            st.markdown(f"**{letter}.**")
            render_text_with_code(option)
        else:
            st.markdown(f"**{letter}.** {html.escape(option)}")


def render_revealed_options(question: pd.Series, validator_answer: str, system_answer: str) -> None:
    """Render answer options with an explicit, colour-independent comparison."""
    for letter in "ABCD":
        option = question[letter]
        labels: list[str] = []
        if validator_answer == system_answer == letter:
            option_class = "answer-match"
            labels.append("Validator & system answer")
        elif letter == validator_answer:
            option_class = "answer-validator"
            labels.append("Validator answer")
        elif letter == system_answer:
            option_class = "answer-system"
            labels.append("System answer")
        else:
            option_class = "answer-neutral"
        label_html = " ".join(f'<span class="answer-badge">{label}</span>' for label in labels)
        st.markdown(
            f'<div class="answer-option {option_class}"><strong>{letter}.</strong> {label_html}</div>',
            unsafe_allow_html=True,
        )
        if has_code(option):
            render_text_with_code(option)
        else:
            st.markdown(f'<div class="answer-option-text {option_class}">{html.escape(option)}</div>', unsafe_allow_html=True)


def set_rating(widget_state_key: str, value: int) -> None:
    st.session_state[widget_state_key] = value


def rating_control(label: str, field: str, question_id: str) -> int | None:
    """Five compact, explicit ratings with no default selection."""
    state_key = widget_key(field, question_id)
    selected = st.session_state.get(state_key)
    choices = st.columns(5, gap="small")
    for score in range(1, 6):
        choices[score - 1].button(
            str(score),
            key=widget_key(f"set_{field}_{score}", question_id),
            type="primary" if selected == score else "secondary",
            on_click=set_rating,
            args=(state_key, score),
            use_container_width=True,
            help=f"Set {label} to rating {score}",
        )
    return st.session_state.get(state_key)


def get_sheet() -> Any:
    """Return the configured worksheet, creating its header if necessary."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        info = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
        )
        client = gspread.authorize(credentials)
        spreadsheet = client.open_by_key(st.secrets["sheet_id"])
        try:
            worksheet = spreadsheet.worksheet("validations")
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.sheet1
        header = worksheet.row_values(1)
        if not header:
            worksheet.append_row(SHEET_COLUMNS, value_input_option="RAW")
        elif set(header) != set(SHEET_COLUMNS):
            raise ValueError("The Google Sheet header does not match the required submission schema.")
        return worksheet
    except KeyError as exc:
        raise RuntimeError("Google Sheets secrets are not configured.") from exc


def backup_records() -> list[dict[str, str]]:
    if not BACKUP_FILE.exists():
        return []
    with BACKUP_FILE.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fetch_submissions() -> list[dict[str, str]]:
    """Read current records; use local saved records only if Sheets is unavailable."""
    try:
        records = get_sheet().get_all_records()
        return [{key: str(value) for key, value in row.items()} for row in records]
    except Exception:
        return backup_records()


def append_backup(record: dict[str, str]) -> None:
    write_header = not BACKUP_FILE.exists()
    with BACKUP_FILE.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SHEET_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(record)


def save_submission(record: dict[str, str]) -> bool:
    """Return True for Sheets persistence, False when the local fallback was used."""
    try:
        sheet = get_sheet()
        header = sheet.row_values(1)
        sheet.append_row([record[column] for column in header], value_input_option="RAW")
        return True
    except Exception:
        append_backup(record)
        return False


def matching_submission(records: list[dict[str, str]], validator_id: str, question_id: str) -> dict[str, str] | None:
    for record in reversed(records):
        if str(record.get("validator_id")) == validator_id and str(record.get("question_id")) == question_id:
            return record
    return None


def rater_submissions() -> list[dict[str, str]]:
    """Avoid a network read on every widget rerun; writes still re-check fresh."""
    if "rater_submissions" not in st.session_state:
        st.session_state.rater_submissions = fetch_submissions()
    return st.session_state.rater_submissions


def sign_out_rater() -> None:
    """Do not leave a validator identity available after entering Admin."""
    question_ids = st.session_state.get("question_ids", [])
    for question_id in question_ids:
        reset_question_form(question_id)
    for state_key in ("rater", "rater_submissions", "current_question_id", "question_ids"):
        st.session_state.pop(state_key, None)


def authenticate_rater() -> None:
    st.subheader("Sign in")

    with st.expander("📋 What you're rating — quick reference"):
        st.markdown("""
        **Technical Accuracy** — is the question, code, and answer key correct?\n
        **Bloom Alignment** — does it require the *labeled* level, not more or less?\n
        **Question Clarity** — is the wording unambiguous?\n
        **Distractor Quality** — are the wrong options plausible?\n
        **Curriculum Fit** — does it belong under its labeled topic?\n
        **Overall Suitability** — would you use this with your own students?\n
    
        **Bloom's Taxonomy** — :blue-background[Remember] (recall) · :blue-background[Understand] (explain, no execution) ·
        :blue-background[Apply] (use a rule on given data) · :blue-background[Analyse] (trace/debug multi-step logic)
        """)
    
    st.write("Sign in to complete your independent item validation.")
    with st.form("rater_login"):
        rater_id = st.text_input("Rater ID").strip()
        passphrase = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")
    if submitted:
        validators = st.secrets.get("validators", {})
        record = validators.get(rater_id)
        if record and passphrase == record.get("passphrase"):
            st.session_state.rater = {
                "id": rater_id, "name": str(record["name"]), "school": str(record["school"]),
            }
            st.rerun()
        st.error("Invalid ID or password")


def render_locked_question(question: pd.Series, submission: dict[str, str]) -> None:
    render_question(question)
    st.subheader("Question options")
    render_revealed_options(question, submission.get("teacher_answer", ""), submission.get("answer_key", ""))
    st.divider()
    st.subheader("Your submitted validation")
    st.write(f"Your answer: **{submission.get('teacher_answer', '')}**")
    st.write(f"Answer-key agreement: **{submission.get('answer_agreement', '')}**")
    rating_values = {
        label: f"{submission.get(field, '')} — {RATING_LABELS.get(str(submission.get(field, '')), 'Not recorded')}"
        for field, label in RATING_FIELDS
    }
    st.dataframe(pd.DataFrame([rating_values]), hide_index=True, use_container_width=True)
    st.write(f"Decision: **{submission.get('decision', '')}**")
    if submission.get("reason_codes"):
        st.write(f"Reason codes: {submission['reason_codes']}")
    if submission.get("comments"):
        st.write(f"Comments: {submission['comments']}")
    st.info("This response is locked to protect the study's independent judgment.")


def render_open_question(question: pd.Series, rater: dict[str, str], submitted_ids: set[str]) -> None:
    question_id = question["ID"]
    render_question(question)
    answer_key = widget_key("teacher_answer", question_id)
    stage_key = widget_key("stage", question_id)

    if st.session_state.get(stage_key) != "revealed":
        option_values = [(letter, question[letter]) for letter in "ABCD"]
        answer = st.radio(
            "Independent answer",
            option_values,
            index=None,
            format_func=option_label,
            key=answer_key,
            label_visibility="collapsed",
        )
        if st.button("Submit answer", disabled=answer is None, type="primary", key=widget_key("reveal", question_id)):
            # Radio widget state is removed once this stage is no longer rendered.
            # Persist the committed blind answer separately for later scoring.
            st.session_state[widget_key("committed_answer", question_id)] = answer[0]
            st.session_state[stage_key] = "revealed"
            st.rerun()
        return

    selected = st.session_state.get(widget_key("committed_answer", question_id))
    system_answer = question["Answer"].strip()
    agreement = "AGREE" if selected == system_answer else "DISAGREE"
    st.markdown("### Answer review")
    render_revealed_options(question, selected, system_answer)
    render_text_with_code(question["Explanation"])
    st.write(f"Your answer-key agreement: **{agreement}**")

    st.markdown("### Item validation")
    st.markdown(
        """
        <table class="rating-scale">
          <tr><th>1</th><th>2</th><th>3</th><th>4</th><th>5</th></tr>
          <tr><td>Major problem</td><td>Significant concern</td><td>Acceptable</td><td>Good</td><td>Excellent</td></tr>
        </table>
        """,
        unsafe_allow_html=True,
    )
    ratings: dict[str, int | None] = {}
    left, right = st.columns(2)
    for index, (field, label) in enumerate(RATING_FIELDS):
        with (left if index < 3 else right):
            st.markdown(f"**{label}**")
            ratings[field] = rating_control(label, field, question_id)

    ratings_complete = all(value is not None for value in ratings.values())
    st.markdown("### Final decision")
    decision = st.radio(
        "Decision", ["ACCEPT", "REVISE", "REJECT"], index=None,
        horizontal=True, key=widget_key("decision", question_id), disabled=not ratings_complete,
        label_visibility="collapsed",
    )
    if not ratings_complete:
        st.caption("Select a rating for all six criteria to unlock the final decision.")
    reasons: list[str] = []
    if decision in {"REVISE", "REJECT"}:
        reasons = st.multiselect("Reason codes", REASON_CODES, key=widget_key("reason_codes", question_id))
    comments = st.text_area("Suggested Correction / Comments (optional)", key=widget_key("comments", question_id))

    can_submit = ratings_complete and selected is not None and decision is not None and (decision == "ACCEPT" or bool(reasons))
    if st.button("Submit validation", type="primary", disabled=not can_submit, key=widget_key("submit", question_id)):
        # Re-read immediately before writing: never trust the on-screen snapshot.
        current_records = fetch_submissions()
        if matching_submission(current_records, rater["id"], question_id):
            st.warning("A submission for this question already exists. It has not been changed.")
            navigate_to(question_id, {str(row.get("question_id")) for row in current_records})
            st.rerun()
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question_id": question_id,
            "topic": question["Topic"],
            "bloom": question["Bloom"],
            "decision": decision,
            "school": rater["school"],
            "question_type": question["Question Type"],
            "teacher_answer": selected,
            "answer_key": system_answer,
            "answer_agreement": agreement,
            "validator_id": rater["id"],
            "validator_name": rater["name"],
            **{field: str(value) for field, value in ratings.items()},
            "reason_codes": " | ".join(reasons),
            "comments": comments.strip(),
        }
        saved_to_sheets = save_submission(record)
        if saved_to_sheets:
            st.success("Validation saved.")
        else:
            st.warning("Google Sheets was unavailable. Your response was saved locally in validations_backup.csv.")
        st.session_state.rater_submissions = current_records + [record]
        submitted_ids.add(question_id)
        unanswered = [qid for qid in st.session_state.question_ids if qid not in submitted_ids]
        if unanswered:
            navigate_to(unanswered[0], submitted_ids)
        st.rerun()


def rater_portal() -> None:
    if "rater" not in st.session_state:
        authenticate_rater()
        return
    questions = get_questions()
    rater = st.session_state.rater
    st.sidebar.markdown(f"**{rater['name']}**")
    st.sidebar.caption(rater["school"])
    st.sidebar.divider()
    records = rater_submissions()
    own_records = [row for row in records if str(row.get("validator_id")) == rater["id"]]
    submitted_ids = {str(row.get("question_id")) for row in own_records}
    st.session_state.question_ids = questions["ID"].tolist()
    if "current_question_id" not in st.session_state:
        unanswered = [qid for qid in st.session_state.question_ids if qid not in submitted_ids]
        st.session_state.current_question_id = unanswered[0] if unanswered else st.session_state.question_ids[0]

    st.sidebar.markdown("### Progress")
    st.sidebar.progress(len(submitted_ids) / len(questions), text=f"{len(submitted_ids)} of {len(questions)} completed")
    st.sidebar.markdown("### Question navigator")
    st.sidebar.caption("✓ submitted · ● current · ○ not yet submitted")
    for row_start in range(0, len(st.session_state.question_ids), 5):
        columns = st.sidebar.columns(5)
        for index, question_id in enumerate(st.session_state.question_ids[row_start:row_start + 5]):
            number = row_start + index + 1
            marker = "✓" if question_id in submitted_ids else ("●" if question_id == st.session_state.current_question_id else "○")
            if columns[index].button(f"{marker} {number}", key=f"nav_{question_id}", use_container_width=True):
                navigate_to(question_id, submitted_ids)
                st.rerun()

    if len(submitted_ids) == len(questions):
        st.success("Validation complete")
        st.write(f"All {len(questions)} responses have been recorded. Thank you for your validation work.")
        return

    current = questions.loc[questions["ID"] == st.session_state.current_question_id].iloc[0]
    locked = matching_submission(own_records, rater["id"], current["ID"])
    if locked:
        render_locked_question(current, locked)
    else:
        render_open_question(current, rater, submitted_ids)


def render_admin_validator_progress(data: pd.DataFrame) -> None:
    """Show a selected rater's completion grid without hiding dashboard totals."""
    questions = get_questions()
    question_ids = questions["ID"].tolist()
    configured = st.secrets.get("validators", {})
    known_ids = list(configured.keys())
    known_ids.extend(identifier for identifier in data["validator_id"].dropna().unique() if identifier not in known_ids)
    if not known_ids:
        st.caption("No validator records are available yet.")
        return

    def display_name(identifier: str) -> str:
        details = configured.get(identifier, {})
        name = details.get("name", identifier)
        school = details.get("school", "")
        return f"{identifier} — {name}" + (f" · {school}" if school else "")

    st.subheader("Validator progress")
    validator_id = st.selectbox("Select validator", known_ids, format_func=display_name)
    submitted = set(
        data.loc[data["validator_id"].eq(validator_id), "question_id"].dropna().astype(str)
    )
    complete = len(submitted.intersection(question_ids))
    st.write(f"**{complete} / {len(question_ids)}** questions submitted")
    st.caption("✓ submitted · ○ not submitted")
    for row_start in range(0, len(question_ids), 8):
        columns = st.columns(8)
        for index, question_id in enumerate(question_ids[row_start:row_start + 8]):
            number = row_start + index + 1
            done = question_id in submitted
            marker = "✓" if done else "○"
            status_class = "admin-grid-done" if done else "admin-grid-open"
            columns[index].markdown(
                f'<div class="admin-grid {status_class}"><strong>{marker}</strong><br><small>{number}</small></div>',
                unsafe_allow_html=True,
            )


def admin_portal() -> None:
    st.title("Admin dashboard")
    if not st.session_state.get("admin_unlocked"):
        password = st.text_input("Admin password", type="password")
        if st.button("Unlock dashboard"):
            if password and password == st.secrets.get("ADMIN_PASSWORD"):
                st.session_state.admin_unlocked = True
                st.rerun()
            st.error("Invalid password")
        return
    data = pd.DataFrame(fetch_submissions(), columns=SHEET_COLUMNS)
    if data.empty:
        st.info("No submissions yet.")
        render_admin_validator_progress(data)
        return
    st.metric("Total submissions", len(data))
    metrics = st.columns(3)
    metrics[0].metric("Questions reviewed", data["question_id"].nunique())
    metrics[1].metric("Participating raters", data["validator_id"].nunique())
    metrics[2].metric("Accept rate", f"{(data['decision'].eq('ACCEPT').mean() * 100):.1f}%")
    render_admin_validator_progress(data)
    st.subheader("Answer-key agreement")
    agreement_counts = (
        data["answer_agreement"].fillna("").replace("", "Not recorded")
        .value_counts().rename_axis("agreement").reset_index(name="responses")
    )
    st.dataframe(agreement_counts, hide_index=True, use_container_width=True)
    st.subheader("Average rating")
    ratings = data[[field for field, _ in RATING_FIELDS]].apply(pd.to_numeric, errors="coerce").mean()
    rating_chart = ratings.rename_axis("criterion").reset_index(name="average_rating")
    rating_chart["average_rating"] = rating_chart["average_rating"].round(2)
    st.dataframe(rating_chart, hide_index=True, use_container_width=True)
    st.subheader("Decision distribution")
    decision_counts = (
        data["decision"].fillna("").replace("", "Not recorded")
        .value_counts().rename_axis("decision").reset_index(name="responses")
    )
    st.dataframe(decision_counts, hide_index=True, use_container_width=True)
    st.subheader("Reason-code frequency")
    reasons = data["reason_codes"].fillna("").str.split(r" \| ").explode()
    reasons = reasons[reasons.ne("")]
    if reasons.empty:
        st.caption("No reason codes have been submitted.")
    else:
        reason_counts = reasons.value_counts().rename_axis("reason_code").reset_index(name="responses")
        st.dataframe(reason_counts, hide_index=True, use_container_width=True)
    st.subheader("Per-question average ratings")
    question_scores = data.assign(**{field: pd.to_numeric(data[field], errors="coerce") for field, _ in RATING_FIELDS})
    st.dataframe(question_scores.groupby("question_id")[[field for field, _ in RATING_FIELDS]].mean(), use_container_width=True)
    st.subheader("Raw submissions")
    st.dataframe(data, use_container_width=True)
    st.download_button("Download CSV", data.to_csv(index=False).encode("utf-8"), "rp1_validations.csv", "text/csv")


def main() -> None:
    st.set_page_config(page_title="MCQ Validation", page_icon="✓", layout="wide")
    st.markdown(
        """
        <style>
        .question-metadata {
            display: flex; flex-wrap: wrap; gap: .45rem;
            margin: .3rem 0 .8rem;
        }
        .question-metadata span {
            background: #e7f0ff; border-left: 4px solid #1769aa;
            color: #123d68; font-size: 1rem; font-weight: 700;
            padding: .42rem .65rem; border-radius: .25rem;
        }
        .question-prompt {
            color: #162a3a; font-size: 1.22rem; font-weight: 650;
            line-height: 1.5; margin-bottom: 1rem;
        }
        .answer-option, .answer-option-text {
            padding: .45rem .7rem; border-left: 5px solid #aab7c4;
        }
        .answer-option { border-radius: .3rem .3rem 0 0; font-size: 1rem; }
        .answer-option-text { border-radius: 0 0 .3rem .3rem; margin-bottom: .55rem; }
        .answer-neutral { background: #f6f8fa; color: #263746; }
        .answer-match { background: #e5f6ea; border-color: #237a42; color: #14532d; }
        .answer-validator { background: #eee9ff; border-color: #6542b5; color: #3f247e; }
        .answer-system { background: #fff3d6; border-color: #b7791f; color: #744210; }
        .answer-badge { font-size: .78rem; font-weight: 700; margin-left: .45rem; }
        .admin-grid { text-align: center; border-radius: .35rem; padding: .4rem 0; margin: .12rem 0; }
        .admin-grid-done { background: #e5f6ea; color: #14532d; border: 1px solid #76b58b; }
        .admin-grid-open { background: #eef2f5; color: #52616d; border: 1px solid #c5d0d8; }
        .rating-scale { width: 100%; table-layout: fixed; border-collapse: separate; border-spacing: .2rem; margin: .2rem 0 .75rem; }
        .rating-scale th, .rating-scale td { width: 20%; text-align: center; border-radius: .3rem; padding: .22rem .15rem; }
        .rating-scale th { color: #27384a; font-size: .9rem; }
        .rating-scale td { font-size: .72rem; color: #384b5d; }
        .rating-scale th:nth-child(1), .rating-scale td:nth-child(1) { background: #fbe9ea; }
        .rating-scale th:nth-child(2), .rating-scale td:nth-child(2) { background: #fff1df; }
        .rating-scale th:nth-child(3), .rating-scale td:nth-child(3) { background: #fff8df; }
        .rating-scale th:nth-child(4), .rating-scale td:nth-child(4) { background: #eaf1fb; }
        .rating-scale th:nth-child(5), .rating-scale td:nth-child(5) { background: #e8f5f1; }
        div.stButton > button[kind="secondary"] { background: #f3f6f9; border-color: #cbd5df; color: #31495f; }
        div.stButton > button[kind="secondary"]:hover { filter: brightness(.96); }
        div.stButton > button[kind="primary"] { background: #496d91; border-color: #3c5c7b; }
        /* The only five-column button rows in the main panel are rating controls. */
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(1) button[kind="secondary"] { background: #fbe9ea; border-color: #ecc6ca; color: #7d3f47; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(2) button[kind="secondary"] { background: #fff1df; border-color: #efd9b7; color: #805d26; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(3) button[kind="secondary"] { background: #fff8df; border-color: #e8ddb1; color: #76652b; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(4) button[kind="secondary"] { background: #eaf1fb; border-color: #c7d8ee; color: #345b82; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(5) button[kind="secondary"] { background: #e8f5f1; border-color: #bee1d6; color: #28665b; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(1) button[kind="primary"] { background: #ba5c67; border-color: #9d4652; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(2) button[kind="primary"] { background: #bf8744; border-color: #9e6b2f; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(3) button[kind="primary"] { background: #a9933b; border-color: #88762b; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(4) button[kind="primary"] { background: #4d78a8; border-color: #3d6088; }
        main div[data-testid="stHorizontalBlock"]:has(> div:nth-child(5)):not(:has(> div:nth-child(6))) > div:nth-child(5) button[kind="primary"] { background: #3e8a7b; border-color: #2f6f63; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.title("MCQ Validation")
    page = st.sidebar.radio("Navigation", ["Rater validation", "Admin dashboard"], label_visibility="collapsed")
    previous_page = st.session_state.get("active_page")
    if page == "Admin dashboard" and previous_page == "Rater validation":
        sign_out_rater()
    elif page == "Rater validation" and previous_page == "Admin dashboard":
        st.session_state.pop("admin_unlocked", None)
    st.session_state.active_page = page
    if page == "Admin dashboard":
        admin_portal()
    else:
        rater_portal()


if __name__ == "__main__":
    main()
