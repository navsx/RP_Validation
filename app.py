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


def authenticate_rater() -> None:
    st.title("MCQ Validation")
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
    render_options(question)
    st.divider()
    st.subheader("Your submitted validation")
    st.write(f"Your answer: **{submission.get('teacher_answer', '')}**")
    st.write(f"Answer-key agreement: **{submission.get('answer_agreement', '')}**")
    rating_values = {label: submission.get(field, "") for field, label in RATING_FIELDS}
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
    agreement = "AGREE" if selected == question["Answer"].strip() else "DISAGREE"
    st.markdown("### Your answer and the answer key")
    render_options(question)
    st.write(f"Your selected answer: **{selected}**")
    st.write(f"Correct answer: **{question['Answer']}**")
    render_text_with_code(question["Explanation"])
    st.write(f"Your answer-key agreement: **{agreement}**")

    st.markdown("### Item validation")
    ratings: dict[str, int] = {}
    left, right = st.columns(2)
    for index, (field, label) in enumerate(RATING_FIELDS):
        with (left if index < 3 else right):
            ratings[field] = st.slider(label, 1, 5, 1, key=widget_key(field, question_id))

    st.markdown("### Final decision")
    decision = st.radio(
        "Decision", ["ACCEPT", "REVISE", "REJECT"], index=None,
        horizontal=True, key=widget_key("decision", question_id),
    )
    reasons: list[str] = []
    if decision in {"REVISE", "REJECT"}:
        reasons = st.multiselect("Reason codes", REASON_CODES, key=widget_key("reason_codes", question_id))
    comments = st.text_area("Suggested Correction / Comments (optional)", key=widget_key("comments", question_id))

    can_submit = selected is not None and decision is not None and (decision == "ACCEPT" or bool(reasons))
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
            "answer_key": question["Answer"].strip(),
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
    st.title("MCQ Validation")
    st.caption(f"Signed in as {rater['name']} · {rater['school']}")
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

    current = questions.loc[questions["ID"] == st.session_state.current_question_id].iloc[0]
    locked = matching_submission(own_records, rater["id"], current["ID"])
    if locked:
        render_locked_question(current, locked)
    else:
        render_open_question(current, rater, submitted_ids)

    if len(submitted_ids) == len(questions):
        st.success("All questions are complete. Thank you for your validation work.")


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
        return
    st.metric("Total submissions", len(data))
    metrics = st.columns(3)
    metrics[0].metric("Questions reviewed", data["question_id"].nunique())
    metrics[1].metric("Participating raters", data["validator_id"].nunique())
    metrics[2].metric("Accept rate", f"{(data['decision'].eq('ACCEPT').mean() * 100):.1f}%")
    st.subheader("Answer-key agreement")
    st.bar_chart(data["answer_agreement"].value_counts())
    st.subheader("Average rating")
    ratings = data[[field for field, _ in RATING_FIELDS]].apply(pd.to_numeric, errors="coerce").mean()
    st.bar_chart(ratings)
    st.subheader("Decision distribution")
    st.bar_chart(data["decision"].value_counts())
    st.subheader("Reason-code frequency")
    reasons = data["reason_codes"].fillna("").str.split(r" \| ").explode()
    reasons = reasons[reasons.ne("")]
    if reasons.empty:
        st.caption("No reason codes have been submitted.")
    else:
        st.bar_chart(reasons.value_counts())
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
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.title("MCQ Validation")
    page = st.sidebar.radio("View", ["Rater validation", "Admin dashboard"])
    if page == "Admin dashboard":
        admin_portal()
    else:
        rater_portal()


if __name__ == "__main__":
    main()
