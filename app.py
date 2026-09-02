# ============================================================
# RP1 MCQ VALIDATION PORTAL
# ============================================================
# Teacher Validation Interface
# + Validator Login
# + Blind Independent Answer
# + System Answer Reveal
# + Item Validation
# + Question Navigator
# + Admin Dashboard
# ============================================================
import os
import re
from datetime import datetime
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="RP1 MCQ Validation",
    page_icon="📝",
    layout="wide"
)
# ============================================================
# CUSTOM CSS
# ============================================================
st.markdown(
    """
    <style>
    .question-card {
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #DDDDDD;
        margin-bottom: 20px;
    }
    .rating-guide {
        padding: 12px;
        border-radius: 8px;
        background-color: #F7F7F7;
        margin-bottom: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True
)
# ============================================================
# VALIDATOR CONFIGURATION
# ============================================================
def get_validators():
    try:
        return st.secrets["validators"]
    except Exception:
        return {}

VALIDATORS = get_validators()
# ============================================================
# ISSUE TAXONOMY
# ============================================================
REASON_CODES = {
    "WRONG_KEY":
        "Wrong answer key",
    "EXPLANATION_ERROR":
        "Explanation error",
    "BLOOM_MISMATCH":
        "Bloom-level mismatch",
    "CLARITY":
        "Clarity / ambiguity problem",
    "DISTRACTOR":
        "Distractor quality problem",
    "CURRICULUM":
        "Curriculum mismatch",
    "MULTIPLE_VALID_ANSWERS":
        "Multiple valid answers",
    "DIFFICULTY":
        "Inappropriate difficulty",
    "OTHER":
        "Other"
}
# ============================================================
# RATING DEFINITIONS
# ============================================================
RATING_MEANINGS = {
    1: "🔴 Major problem",
    2: "🟠 Significant concern",
    3: "🟡 Moderate concern",
    4: "🔵 Minor concern",
    5: "🟢 No concern"
}
RATING_COLUMNS = [
    "technical_accuracy",
    "bloom_alignment",
    "clarity",
    "distractor_quality",
    "curriculum_fit",
    "overall_suitability"
]
# ============================================================
# SUBMISSION COLUMNS
# ============================================================
SUBMISSION_COLUMNS = [
    "timestamp",
    "validator_id",
    "validator_name",
    "school",
    "question_id",
    "topic",
    "question_type",
    "bloom",
    # Independent answer
    "teacher_answer",
    "answer_key",
    "answer_agreement",
    # Ratings
    "technical_accuracy",
    "bloom_alignment",
    "clarity",
    "distractor_quality",
    "curriculum_fit",
    "overall_suitability",
    # Final decision
    "decision",
    # Issues
    "reason_codes",
    "comments"
]
# ============================================================
# LOAD QUESTION DATA
# ============================================================
@st.cache_data
def load_questions():
    df = pd.read_csv(
        "mcq_repository.csv"
    )
    df["ID"] = df["ID"].astype(str)
    return df
questions_df = load_questions()
# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================
def init_sheet():
    creds_json = (
        st.secrets[
            "gcp_service_account"
        ]
    )
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    credentials = (
        Credentials
        .from_service_account_info(
            creds_json,
            scopes=scopes
        )
    )
    client = (
        gspread.authorize(
            credentials
        )
    )
    spreadsheet = (
        client.open_by_key(
            st.secrets["sheet_id"]
        )
    )
    return spreadsheet.sheet1
# ============================================================
# FETCH SUBMISSIONS
# ============================================================
@st.cache_data(ttl=20)
def fetch_submissions():
    try:
        sheet = init_sheet()
        data = (
            sheet.get_all_records()
        )
        if data:
            df = pd.DataFrame(data)
            df.columns = [
                str(column)
                .strip()
                .lower()
                for column
                in df.columns
            ]
            return df
    except Exception:
        pass
    # --------------------------------------------------------
    # LOCAL BACKUP
    # --------------------------------------------------------
    try:
        if os.path.exists(
            "validations_backup.csv"
        ):
            df = pd.read_csv(
                "validations_backup.csv"
            )
            df.columns = [
                str(column)
                .strip()
                .lower()
                for column
                in df.columns
            ]
            return df
    except Exception:
        pass
    return pd.DataFrame()
# ============================================================
# SAVE SUBMISSION
# ============================================================
def save_submission(
    submission
):
    google_error = ""
    # --------------------------------------------------------
    # GOOGLE SHEETS
    # --------------------------------------------------------
    try:
        sheet = init_sheet()
        existing_header = (
            sheet.row_values(1)
        )
        # ----------------------------------------------------
        # CREATE HEADER
        # ----------------------------------------------------
        if not existing_header:
            sheet.append_row(
                SUBMISSION_COLUMNS
            )
            existing_header = (
                SUBMISSION_COLUMNS.copy()
            )
        # ----------------------------------------------------
        # ADD NEW COLUMNS IF NECESSARY
        # ----------------------------------------------------
        missing_columns = [
            column
            for column
            in SUBMISSION_COLUMNS
            if column
            not in existing_header
        ]
        if missing_columns:
            updated_header = (
                existing_header
                + missing_columns
            )
            sheet.update(
                range_name="1:1",
                values=[
                    updated_header
                ]
            )
            existing_header = (
                updated_header
            )
        # ----------------------------------------------------
        # CREATE ROW
        # ----------------------------------------------------
        row = [
            submission.get(
                column,
                ""
            )
            for column
            in existing_header
        ]
        sheet.append_row(
            row
        )
        return (
            True,
            "Validation saved successfully."
        )
    except Exception as error:
        google_error = str(error)
    # --------------------------------------------------------
    # LOCAL BACKUP
    # --------------------------------------------------------
    try:
        backup_file = (
            "validations_backup.csv"
        )
        backup_exists = (
            os.path.exists(
                backup_file
            )
        )
        backup_df = pd.DataFrame(
            [submission]
        )
        backup_df = (
            backup_df.reindex(
                columns=SUBMISSION_COLUMNS
            )
        )
        backup_df.to_csv(
            backup_file,
            mode="a",
            header=not backup_exists,
            index=False
        )
        return (
            True,
            "Google Sheets was unavailable. "
            "Response saved to local backup."
        )
    except Exception as error:
        return (
            False,
            "Unable to save validation.\n\n"
            f"Google Sheets error: "
            f"{google_error}\n\n"
            f"Backup error: {error}"
        )
# ============================================================
# QUESTION HELPERS
# ============================================================
def get_question_row(
    question_id
):
    return (
        questions_df[
            questions_df["ID"]
            == str(question_id)
        ]
        .iloc[0]
    )
# ============================================================
# CODE FORMATTING
# ============================================================
def clean_code(
    code
):
    if code is None:
        return ""
    code = str(code)
    # Convert literal \n
    # stored in CSV into real line breaks
    code = code.replace(
        "\\n",
        "\n"
    )
    # Convert literal \t
    code = code.replace(
        "\\t",
        "\t"
    )
    return code.strip()
# ============================================================
# RENDER TEXT WITH CODE
# ============================================================
def render_text_with_code(
    text
):
    if pd.isna(text):
        return
    text = str(text)
    # --------------------------------------------------------
    # Convert literal line breaks
    # --------------------------------------------------------
    text = text.replace(
        "\\n",
        "\n"
    )
    # --------------------------------------------------------
    # Pattern
    # --------------------------------------------------------
    pattern = (
        r"\{\{CODE\}\}"
        r"(.*?)"
        r"\{\{/CODE\}\}"
    )
    parts = re.split(
        pattern,
        text,
        flags=re.DOTALL
    )
    for index, part in enumerate(parts):
        # ----------------------------------------------------
        # NORMAL TEXT
        # ----------------------------------------------------
        if index % 2 == 0:
            if part.strip():
                st.markdown(
                    part.strip()
                )
        # ----------------------------------------------------
        # CODE
        # ----------------------------------------------------
        else:
            code = clean_code(
                part
            )
            if code:
                st.code(
                    code,
                    language="python"
                )
# ============================================================
# OPTION DISPLAY TEXT
# ============================================================
def get_option_display_text(
    letter,
    text
):
    text = str(text)
    text = text.replace(
        "\\n",
        "\n"
    )
    # Remove code markers for radio labels
    text = text.replace(
        "{{CODE}}",
        ""
    )
    text = text.replace(
        "{{/CODE}}",
        ""
    )
    return (
        f"{letter}. {text}"
    )
# ============================================================
# SESSION STATE INITIALIZATION
# ============================================================
def initialize_session_state():
    defaults = {
        "logged_in":
            False,
        "validator_id":
            None,
        "validator_name":
            None,
        "school":
            None,
        "current_question":
            None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = (
                value
            )
initialize_session_state()
# ============================================================
# QUESTION-SPECIFIC KEYS
# ============================================================
def key_for(
    name,
    question_id
):
    return (
        f"{name}_{question_id}"
    )
# ============================================================
# ANSWER SUBMITTED STATUS
# ============================================================
def is_answer_submitted(
    question_id
):
    return (
        st.session_state.get(
            key_for(
                "answer_submitted",
                question_id
            ),
            False
        )
    )
# ============================================================
# SET ANSWER SUBMITTED
# ============================================================
def submit_independent_answer(
    question_id
):
    answer = (
        st.session_state.get(
            key_for(
                "teacher_answer",
                question_id
            )
        )
    )
    if answer is None:
        return False
    st.session_state[
        key_for(
            "answer_submitted",
            question_id
        )
    ] = True
    return True
# ============================================================
# GET COMPLETED QUESTIONS
# ============================================================
def get_completed_questions(
    submissions,
    validator_id
):
    if submissions.empty:
        return set()
    if (
        "validator_id"
        not in submissions.columns
    ):
        return set()
    if (
        "question_id"
        not in submissions.columns
    ):
        return set()
    validator_data = (
        submissions[
            submissions[
                "validator_id"
            ]
            .astype(str)
            == str(validator_id)
        ]
    )
    return set(
        validator_data[
            "question_id"
        ]
        .astype(str)
        .tolist()
    )
# ============================================================
# CLEAR QUESTION DRAFT
# ============================================================
def clear_question_state(
    question_id
):
    prefixes = [
        "teacher_answer",
        "answer_submitted",
        "technical_accuracy",
        "bloom_alignment",
        "clarity",
        "distractor_quality",
        "curriculum_fit",
        "overall_suitability",
        "decision",
        "reason_codes",
        "comments"
    ]
    for prefix in prefixes:
        key = key_for(
            prefix,
            question_id
        )
        if key in st.session_state:
            del st.session_state[key]
# ============================================================
# GET NEXT UNANSWERED QUESTION
# ============================================================
def get_next_unanswered_question(
    current_question,
    completed_questions
):
    question_ids = (
        questions_df["ID"]
        .astype(str)
        .tolist()
    )
    try:
        current_index = (
            question_ids.index(
                str(current_question)
            )
        )
    except ValueError:
        current_index = -1
    # --------------------------------------------------------
    # Search after current question
    # --------------------------------------------------------
    for question_id in (
        question_ids[
            current_index + 1:
        ]
    ):
        if question_id not in completed_questions:
            return question_id
    # --------------------------------------------------------
    # Search from beginning
    # --------------------------------------------------------
    for question_id in question_ids:
        if question_id not in completed_questions:
            return question_id
    return None
# ============================================================
# ADMIN PASSWORD
# ============================================================
def get_admin_password():
    try:
        return st.secrets.get(
            "ADMIN_PASSWORD",
            None
        )
    except Exception:
        return None
# ============================================================
# SIDEBAR
# ============================================================
st.sidebar.title(
    "📝 RP1 Validation"
)
st.sidebar.markdown(
    "---"
)
# ============================================================
# LOGIN SCREEN
# ============================================================
if not st.session_state.logged_in:
    st.title(
        "MCQ Teacher Validation Study"
    )
    st.markdown(
        """
        Please log in using your assigned
        **Validator ID and passphrase**.
        You will first independently answer each question.
        The system answer and explanation will then be shown
        before you complete the validation.
        """
    )
    st.markdown("---")
    validator_id = st.selectbox(
        "Validator ID",
        options=[
            ""
        ]
        + list(
            VALIDATORS.keys()
        ),
        format_func=lambda value:
            (
                "Select Validator ID"
            )
            if value == ""
            else value
    )
    passphrase = st.text_input(
        "Passphrase",
        type="password"
    )
    if st.button(
        "Start Validation",
        type="primary"
    ):
        if validator_id == "":
            st.error(
                "Please select your Validator ID."
            )
            st.stop()
        if not passphrase:
            st.error(
                "Please enter your passphrase."
            )
            st.stop()
        if not school.strip():
            st.error(
                "Please enter your School / Institution."
            )
            st.stop()
        # ----------------------------------------------------
        # VALIDATE PASSPHRASE
        # ----------------------------------------------------
        expected_passphrase = (
            VALIDATORS[
                validator_id
            ][
                "passphrase"
            ]
        )
        if passphrase != expected_passphrase:
            st.error(
                "Incorrect passphrase."
            )
            st.stop()
        # ----------------------------------------------------
        # LOGIN
        # ----------------------------------------------------
        st.session_state.logged_in = (
            True
        )
        st.session_state.validator_id = (
            validator_id
        )
        st.session_state.validator_name = (
            VALIDATORS[
                validator_id
            ][
                "name"
            ]
        )
        st.session_state.school = (
            school.strip()
        )
        # ----------------------------------------------------
        # GET FIRST QUESTION
        # ----------------------------------------------------
        submissions = (
            fetch_submissions()
        )
        completed = (
            get_completed_questions(
                submissions,
                validator_id
            )
        )
        all_questions = (
            questions_df["ID"]
            .astype(str)
            .tolist()
        )
        remaining = [
            question_id
            for question_id
            in all_questions
            if question_id
            not in completed
        ]
        if remaining:
            st.session_state.current_question = (
                remaining[0]
            )
        st.rerun()
    st.stop()
# ============================================================
# AFTER LOGIN
# ============================================================
validator_id = (
    st.session_state.validator_id
)
validator_name = (
    st.session_state.validator_name
)
school = (
    st.session_state.school
)
# ============================================================
# SIDEBAR GREETING
# ============================================================
st.sidebar.success(
    f"Welcome,\n{validator_name}!"
)
st.sidebar.caption(
    f"Validator: {validator_id}"
)
st.sidebar.caption(
    f"School: {school}"
)
st.sidebar.markdown(
    "---"
)
# ============================================================
# ADMIN ACCESS
# ============================================================
admin_password = (
    get_admin_password()
)
mode_options = [
    "📝 Validation"
]
if admin_password:
    mode_options.append(
        "🔐 Admin"
    )
mode = st.sidebar.radio(
    "Mode",
    mode_options
)
# ============================================================
# ADMIN DASHBOARD
# ============================================================
if mode == "🔐 Admin":
    st.title(
        "🔐 Administrator Dashboard"
    )
    entered_password = st.text_input(
        "Administrator Password",
        type="password"
    )
    if entered_password != admin_password:
        st.info(
            "Enter the administrator password."
        )
        st.stop()
    results_df = (
        fetch_submissions()
    )
    if results_df.empty:
        st.info(
            "No validation responses yet."
        )
        st.stop()
    # ========================================================
    # SUMMARY
    # ========================================================
    st.subheader(
        "Summary"
    )
    col1, col2, col3, col4 = (
        st.columns(4)
    )
    with col1:
        st.metric(
            "Total Submissions",
            len(results_df)
        )
    with col2:
        st.metric(
            "Questions Reviewed",
            results_df[
                "question_id"
            ].nunique()
            if "question_id"
            in results_df.columns
            else 0
        )
    with col3:
        st.metric(
            "Validators",
            results_df[
                "validator_id"
            ].nunique()
            if "validator_id"
            in results_df.columns
            else 0
        )
    with col4:
        if (
            "decision"
            in results_df.columns
        ):
            accept_rate = (
                results_df[
                    "decision"
                ]
                .astype(str)
                .str.upper()
                .eq("ACCEPT")
                .mean()
                * 100
            )
        else:
            accept_rate = 0
        st.metric(
            "Accept Rate",
            f"{accept_rate:.1f}%"
        )
    # ========================================================
    # DECISION SUMMARY
    # ========================================================
    st.markdown("---")
    st.subheader(
        "Decision Distribution"
    )
    if (
        "decision"
        in results_df.columns
    ):
        decision_counts = (
            results_df[
                "decision"
            ]
            .value_counts()
            .reset_index()
        )
        decision_counts.columns = [
            "Decision",
            "Count"
        ]
        st.dataframe(
            decision_counts,
            use_container_width=True
        )
    # ========================================================
    # ANSWER AGREEMENT
    # ========================================================
    st.markdown("---")
    st.subheader(
        "Independent Answer Agreement"
    )
    if (
        "answer_agreement"
        in results_df.columns
    ):
        agreement_counts = (
            results_df[
                "answer_agreement"
            ]
            .value_counts()
            .reset_index()
        )
        agreement_counts.columns = [
            "Agreement",
            "Count"
        ]
        st.dataframe(
            agreement_counts,
            use_container_width=True
        )
    # ========================================================
    # AVERAGE RATINGS
    # ========================================================
    st.markdown("---")
    st.subheader(
        "Average Ratings"
    )
    available_ratings = [
        column
        for column
        in RATING_COLUMNS
        if column
        in results_df.columns
    ]
    if available_ratings:
        for column in available_ratings:
            results_df[column] = (
                pd.to_numeric(
                    results_df[column],
                    errors="coerce"
                )
            )
        averages = (
            results_df[
                available_ratings
            ]
            .mean()
            .round(2)
            .reset_index()
        )
        averages.columns = [
            "Criterion",
            "Average"
        ]
        st.dataframe(
            averages,
            use_container_width=True
        )
    # ========================================================
    # REASON CODES
    # ========================================================
    st.markdown("---")
    st.subheader(
        "Issue Code Summary"
    )
    if (
        "reason_codes"
        in results_df.columns
    ):
        all_codes = []
        for code_text in (
            results_df[
                "reason_codes"
            ]
            .dropna()
        ):
            codes = [
                code.strip()
                for code
                in str(code_text).split("|")
                if code.strip()
            ]
            all_codes.extend(
                codes
            )
        if all_codes:
            code_counts = (
                pd.Series(
                    all_codes
                )
                .value_counts()
                .reset_index()
            )
            code_counts.columns = [
                "Issue Code",
                "Count"
            ]
            st.dataframe(
                code_counts,
                use_container_width=True
            )
        else:
            st.info(
                "No issue codes recorded yet."
            )
    # ========================================================
    # RAW DATA
    # ========================================================
    st.markdown("---")
    st.subheader(
        "Raw Validation Data"
    )
    st.dataframe(
        results_df,
        use_container_width=True
    )
    # ========================================================
    # EXPORT
    # ========================================================
    csv_data = (
        results_df
        .to_csv(
            index=False
        )
        .encode("utf-8")
    )
    st.download_button(
        "⬇️ Download CSV",
        csv_data,
        file_name=(
            "rp1_validation_results.csv"
        ),
        mime="text/csv"
    )
    st.stop()
# ============================================================
# VALIDATION MODE
# ============================================================
st.title(
    "MCQ Teacher Validation"
)
st.caption(
    "Independent Answer → "
    "System Answer & Explanation → "
    "Item Validation"
)
# ============================================================
# LOAD SUBMISSIONS
# ============================================================
submissions_df = (
    fetch_submissions()
)
completed_questions = (
    get_completed_questions(
        submissions_df,
        validator_id
    )
)
all_question_ids = (
    questions_df["ID"]
    .astype(str)
    .tolist()
)
total_questions = (
    len(all_question_ids)
)
completed_count = (
    len(completed_questions)
)
# ============================================================
# ALL QUESTIONS COMPLETE
# ============================================================
if (
    completed_count
    >= total_questions
):
    st.success(
        "🎉 You have completed all questions."
    )
    st.stop()
# ============================================================
# INITIAL QUESTION
# ============================================================
if (
    st.session_state.current_question
    is None
):
    next_question = (
        get_next_unanswered_question(
            None,
            completed_questions
        )
    )
    st.session_state.current_question = (
        next_question
    )
# ============================================================
# SIDEBAR PROGRESS
# ============================================================
progress = (
    completed_count
    / total_questions
)
st.sidebar.markdown(
    "### Progress"
)
st.sidebar.progress(
    progress
)
st.sidebar.write(
    f"**{completed_count} / "
    f"{total_questions} completed**"
)
# ============================================================
# QUESTION NAVIGATOR
# ============================================================
st.sidebar.markdown(
    "---"
)
st.sidebar.markdown(
    "### Question Navigator"
)
st.sidebar.caption(
    "🟩 Submitted  |  "
    "🔵 Current  |  "
    "⚪ Not submitted"
)
# ============================================================
# NAVIGATION GRID
# ============================================================
QUESTIONS_PER_ROW = 5
for row_start in range(
    0,
    total_questions,
    QUESTIONS_PER_ROW
):
    row_questions = (
        all_question_ids[
            row_start:
            row_start
            + QUESTIONS_PER_ROW
        ]
    )
    columns = st.sidebar.columns(
        QUESTIONS_PER_ROW
    )
    for index, question_id in enumerate(
        row_questions
    ):
        question_number = (
            all_question_ids.index(
                question_id
            )
            + 1
        )
        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------
        if question_id in completed_questions:
            label = (
                f"🟩 {question_number}"
            )
        elif (
            question_id
            == st.session_state.current_question
        ):
            label = (
                f"🔵 {question_number}"
            )
        else:
            label = (
                f"⚪ {question_number}"
            )
        # ----------------------------------------------------
        # BUTTON
        # ----------------------------------------------------
        if columns[index].button(
            label,
            key=(
                f"nav_{question_id}"
            ),
            use_container_width=True
        ):
            st.session_state.current_question = (
                question_id
            )
            st.rerun()
# ============================================================
# CURRENT QUESTION
# ============================================================
current_question = (
    st.session_state.current_question
)
# ============================================================
# SUBMITTED QUESTION REVIEW
# ============================================================
if current_question in completed_questions:
    q_row = get_question_row(
        current_question
    )
    question_number = (
        all_question_ids.index(
            current_question
        )
        + 1
    )
    st.info(
        "This question has already been submitted and is locked."
    )
    st.subheader(
        f"Question {question_number}"
    )
    render_text_with_code(
        q_row["Question"]
    )
    st.markdown(
        "### Options"
    )
    for letter in [
        "A",
        "B",
        "C",
        "D"
    ]:
        st.markdown(
            f"**{letter}.**"
        )
        render_text_with_code(
            q_row[letter]
        )
    st.markdown("---")
    st.success(
        "Submitted validation is locked."
    )
    st.stop()
# ============================================================
# CURRENT QUESTION DATA
# ============================================================
q_row = get_question_row(
    current_question
)
question_number = (
    all_question_ids.index(
        current_question
    )
    + 1
)
# ============================================================
# QUESTION HEADER
# ============================================================
st.subheader(
    f"Question {question_number} "
    f"of {total_questions}"
)
# ============================================================
# QUESTION
# ============================================================
with st.container(border=True):
    render_text_with_code(
        q_row["Question"]
    )
# ============================================================
# OPTIONS
# ============================================================
st.markdown(
    "### Select Your Answer"
)
# ------------------------------------------------------------
# ACTUAL OPTION TEXT
# ------------------------------------------------------------
option_values = [
    "A",
    "B",
    "C",
    "D"
]
def option_format(
    letter
):
    return get_option_display_text(
        letter,
        q_row[letter]
    )
# ============================================================
# STAGE 1
# ============================================================
if not is_answer_submitted(
    current_question
):
    selected_answer = st.radio(
        "Select the answer you believe is correct:",
        options=option_values,
        index=None,
        format_func=option_format,
        key=key_for(
            "teacher_answer",
            current_question
        )
    )
    st.markdown("---")
    if st.button(
        "Submit My Answer",
        type="primary",
        use_container_width=True,
        key=key_for(
            "submit_answer",
            current_question
        )
    ):
        if selected_answer is None:
            st.warning(
                "Please select an answer first."
            )
        else:
            submit_independent_answer(
                current_question
            )
            st.rerun()
    st.stop()
# ============================================================
# STAGE 2
# SYSTEM ANSWER
# ============================================================
teacher_answer = (
    st.session_state.get(
        key_for(
            "teacher_answer",
            current_question
        )
    )
)
answer_key = str(
    q_row["Answer"]
).strip()
# ------------------------------------------------------------
# AGREEMENT
# ------------------------------------------------------------
if teacher_answer == answer_key:
    agreement = "AGREE"
else:
    agreement = "DISAGREE"
# ============================================================
# ANSWER REVEAL
# ============================================================
st.markdown("---")
st.subheader(
    "System Answer"
)
st.markdown(
    f"**Your Answer:** "
    f"`{teacher_answer}`"
)
st.markdown(
    f"**System Answer:** "
    f"`{answer_key}`"
)
if agreement == "AGREE":
    st.success(
        "Your answer matches the system answer."
    )
else:
    st.warning(
        "Your answer does not match the system answer."
    )
# ============================================================
# EXPLANATION
# ============================================================
st.markdown(
    "### System Explanation"
)
with st.container(border=True):
    render_text_with_code(
        q_row["Explanation"]
    )
# ============================================================
# VALIDATION
# ============================================================
st.markdown("---")
st.header(
    "Item Validation"
)
st.markdown(
    """
    **Rating Guide**
    🔴 **1 = Major problem**  
    🟠 **2 = Significant concern**  
    🟡 **3 = Moderate concern**  
    🔵 **4 = Minor concern**  
    🟢 **5 = No concern**
    """
)
st.caption(
    "All ratings begin at 🔴 1. "
    "Adjust them according to your evaluation."
)
# ============================================================
# RATING HELPER
# ============================================================
def rating_slider(
    label,
    state_name,
    help_text
):
    value = st.slider(
        label,
        min_value=1,
        max_value=5,
        value=1,
        step=1,
        key=key_for(
            state_name,
            current_question
        ),
        help=help_text
    )
    st.caption(
        RATING_MEANINGS[value]
    )
    return value
# ============================================================
# RATINGS
# ============================================================
left_col, right_col = (
    st.columns(2)
)
with left_col:
    technical_accuracy = rating_slider(
        "Technical Accuracy",
        "technical_accuracy",
        (
            "Are the question, options, "
            "answer key, and explanation "
            "technically correct?"
        )
    )
    bloom_alignment = rating_slider(
        "Bloom-Level Alignment",
        "bloom_alignment",
        (
            "Does the item require the intended "
            "level of cognitive processing?"
        )
    )
    clarity = rating_slider(
        "Clarity",
        "clarity",
        (
            "Is the wording clear and unambiguous?"
        )
    )
with right_col:
    distractor_quality = rating_slider(
        "Distractor Quality",
        "distractor_quality",
        (
            "Are incorrect options plausible "
            "and meaningful?"
        )
    )
    curriculum_fit = rating_slider(
        "Curriculum Fit",
        "curriculum_fit",
        (
            "Is the question appropriate for "
            "the intended curriculum?"
        )
    )
    overall_suitability = rating_slider(
        "Overall Suitability",
        "overall_suitability",
        (
            "Overall suitability of the item "
            "for the intended assessment."
        )
    )
# ============================================================
# FINAL DECISION
# ============================================================
st.markdown("---")
st.subheader(
    "Final Decision"
)
decision = st.radio(
    "Select your final decision:",
    options=[
        "ACCEPT",
        "REVISE",
        "REJECT"
    ],
    index=None,
    horizontal=True,
    key=key_for(
        "decision",
        current_question
    )
)
# ============================================================
# REASON CODES
# ============================================================
selected_reason_codes = []
if decision in [
    "REVISE",
    "REJECT"
]:
    st.markdown(
        "### Issue Codes"
    )
    selected_reason_codes = (
        st.multiselect(
            "Select all applicable issues:",
            options=list(
                REASON_CODES.keys()
            ),
            format_func=lambda code:
                (
                    f"{code} — "
                    f"{REASON_CODES[code]}"
                ),
            key=key_for(
                "reason_codes",
                current_question
            )
        )
    )
# ============================================================
# COMMENTS
# ============================================================
comments = st.text_area(
    "Comments / Suggested Correction",
    placeholder=(
        "Optional: Describe the issue "
        "or suggest a correction."
    ),
    key=key_for(
        "comments",
        current_question
    )
)
# ============================================================
# FINAL SUBMISSION
# ============================================================
st.markdown("---")
if st.button(
    "Submit Validation →",
    type="primary",
    use_container_width=True,
    key=key_for(
        "submit_validation",
        current_question
    )
):
    # --------------------------------------------------------
    # DECISION REQUIRED
    # --------------------------------------------------------
    if decision is None:
        st.warning(
            "Please select a final decision."
        )
        st.stop()
    # --------------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------------
    st.cache_data.clear()
    fresh_submissions = (
        fetch_submissions()
    )
    fresh_completed = (
        get_completed_questions(
            fresh_submissions,
            validator_id
        )
    )
    if current_question in fresh_completed:
        st.error(
            "This question has already been submitted."
        )
        st.stop()
    # --------------------------------------------------------
    # CREATE SUBMISSION
    # --------------------------------------------------------
    submission = {
        "timestamp":
            datetime.now().isoformat(),
        "validator_id":
            validator_id,
        "validator_name":
            validator_name,
        "school":
            school,
        "question_id":
            current_question,
        "topic":
            q_row["Topic"],
        "question_type":
            q_row[
                "Question Type"
            ],
        "bloom":
            q_row["Bloom"],
        # ----------------------------------------------------
        # INDEPENDENT ANSWER
        # ----------------------------------------------------
        "teacher_answer":
            teacher_answer,
        "answer_key":
            answer_key,
        "answer_agreement":
            agreement,
        # ----------------------------------------------------
        # RATINGS
        # ----------------------------------------------------
        "technical_accuracy":
            technical_accuracy,
        "bloom_alignment":
            bloom_alignment,
        "clarity":
            clarity,
        "distractor_quality":
            distractor_quality,
        "curriculum_fit":
            curriculum_fit,
        "overall_suitability":
            overall_suitability,
        # ----------------------------------------------------
        # DECISION
        # ----------------------------------------------------
        "decision":
            decision,
        # ----------------------------------------------------
        # ISSUES
        # ----------------------------------------------------
        "reason_codes":
            " | ".join(
                selected_reason_codes
            ),
        "comments":
            comments
    }
    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------
    success, message = (
        save_submission(
            submission
        )
    )
    if success:
        # ----------------------------------------------------
        # CLEAR CACHE
        # ----------------------------------------------------
        st.cache_data.clear()
        # ----------------------------------------------------
        # CLEAR QUESTION STATE
        # ----------------------------------------------------
        clear_question_state(
            current_question
        )
        # ----------------------------------------------------
        # REFRESH SUBMISSIONS
        # ----------------------------------------------------
        refreshed_submissions = (
            fetch_submissions()
        )
        refreshed_completed = (
            get_completed_questions(
                refreshed_submissions,
                validator_id
            )
        )
        # ----------------------------------------------------
        # FIND NEXT QUESTION
        # ----------------------------------------------------
        next_question = (
            get_next_unanswered_question(
                current_question,
                refreshed_completed
            )
        )
        # ----------------------------------------------------
        # MOVE
        # ----------------------------------------------------
        if next_question:
            st.session_state.current_question = (
                next_question
            )
            st.rerun()
        else:
            st.success(
                "🎉 All questions completed. "
                "Thank you for your participation."
            )
    else:
        st.error(
            message
        )
