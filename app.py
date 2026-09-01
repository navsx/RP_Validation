# ============================================================
# RP1 MCQ VALIDATION PORTAL
# Teacher Validation + Admin Dashboard
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
    page_title="MCQ Validation Portal",
    page_icon="📝",
    layout="wide"
)


# ============================================================
# CONFIGURATION
# ============================================================

# Replace placeholder names before the actual validation study.
# Rater IDs should remain stable across sessions.

APPROVED_RATERS = {
    "R01": "Approved Rater 01",
    "R02": "Approved Rater 02",
    "R03": "Approved Rater 03",
    "R04": "Approved Rater 04",
    "R05": "Approved Rater 05",
}


# Structured issue taxonomy

REASON_CODES = {
    "WRONG_KEY": "Wrong answer key",
    "EXPLANATION_ERROR": "Explanation error",
    "BLOOM_MISMATCH": "Bloom-level mismatch",
    "CLARITY": "Clarity / ambiguous wording",
    "DISTRACTOR": "Distractor quality problem",
    "CURRICULUM": "Curriculum mismatch",
    "MULTIPLE_VALID_ANSWERS": "Multiple valid answers",
    "DIFFICULTY": "Inappropriate difficulty",
    "OTHER": "Other",
}


RATING_COLUMNS = [
    "accuracy",
    "bloom_align",
    "clarity",
    "distractor",
    "curriculum",
    "overall",
]


SUBMISSION_COLUMNS = [
    "timestamp",

    "rater_id",
    "rater_name",
    "school",

    "question_id",

    # Research/admin metadata
    "topic",
    "question_type",
    "bloom",

    # Independent solving
    "teacher_answer",
    "answer_key",
    "answer_agreement",

    # Ratings
    "accuracy",
    "bloom_align",
    "clarity",
    "distractor",
    "curriculum",
    "overall",

    # Decision
    "decision",

    # Issues/comments
    "reasons",
    "correction",
]


# ============================================================
# LOAD MCQ DATA
# ============================================================

@st.cache_data
def load_questions():

    df = pd.read_csv("mcq_repository.csv")

    df["ID"] = df["ID"].astype(str)

    return df


questions_df = load_questions()


# ============================================================
# GOOGLE SHEETS CONNECTION
# ============================================================

def init_sheet():

    creds_json = st.secrets["gcp_service_account"]

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets"
    ]

    creds = Credentials.from_service_account_info(
        creds_json,
        scopes=scopes
    )

    client = gspread.authorize(creds)

    return client.open_by_key(
        st.secrets["sheet_id"]
    ).sheet1


# ============================================================
# FETCH EXISTING SUBMISSIONS
# ============================================================

@st.cache_data(ttl=30)
def fetch_submissions():

    # Try Google Sheets first

    try:

        sheet = init_sheet()

        data = sheet.get_all_records()

        if data:

            df = pd.DataFrame(data)

            df.columns = [
                str(column).strip().lower()
                for column in df.columns
            ]

            return df

    except Exception:
        pass


    # Local CSV fallback

    try:

        if os.path.exists(
            "validations_backup.csv"
        ):

            df = pd.read_csv(
                "validations_backup.csv"
            )

            df.columns = [
                str(column).strip().lower()
                for column in df.columns
            ]

            return df

    except Exception:
        pass


    return pd.DataFrame()


# ============================================================
# SAVE SUBMISSION
# ============================================================

def save_submission(submission_dict):

    google_error = ""


    # --------------------------------------------------------
    # GOOGLE SHEETS
    # --------------------------------------------------------

    try:

        sheet = init_sheet()

        existing_header = sheet.row_values(1)


        # Empty sheet

        if not existing_header:

            sheet.append_row(
                SUBMISSION_COLUMNS
            )

            existing_header = (
                SUBMISSION_COLUMNS.copy()
            )


        # Add missing columns

        missing_columns = [

            column

            for column in SUBMISSION_COLUMNS

            if column not in existing_header

        ]


        if missing_columns:

            updated_header = (
                existing_header
                + missing_columns
            )

            sheet.update(
                "1:1",
                [updated_header]
            )

            existing_header = updated_header


        # Create row according to
        # current Google Sheet column order

        row = [

            submission_dict.get(
                column,
                ""
            )

            for column
            in existing_header

        ]


        sheet.append_row(row)


        return (
            True,
            "Saved successfully."
        )


    except Exception as error:

        google_error = str(error)


    # --------------------------------------------------------
    # LOCAL CSV FALLBACK
    # --------------------------------------------------------

    try:

        backup_file = (
            "validations_backup.csv"
        )


        backup_exists = os.path.exists(
            backup_file
        )


        backup_df = pd.DataFrame(
            [submission_dict]
        )


        backup_df = backup_df.reindex(
            columns=SUBMISSION_COLUMNS
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
            "Your response was saved locally."

        )


    except Exception as backup_error:

        return (

            False,

            "Could not save your response.\n\n"
            f"Google Sheets error: "
            f"{google_error}\n\n"
            f"Backup error: "
            f"{backup_error}"

        )


# ============================================================
# CODE RENDERING
# ============================================================

def render_text_with_code(text):

    """
    Renders normal text normally and content between:

    {{CODE}}
    ...
    {{/CODE}}

    as a Python code block.
    """

    if pd.isna(text):

        return


    text = str(text)


    # Convert literal \n into real line breaks

    text = text.replace(
        "\\n",
        "\n"
    )


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

        # Normal text

        if index % 2 == 0:

            if part.strip():

                st.markdown(
                    part.strip()
                )


        # Code block

        else:

            st.code(

                part.strip(),

                language="python"

            )


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_question_row(question_id):

    return questions_df[
        questions_df["ID"] == question_id
    ].iloc[0]


def get_rater_submissions(
    submissions_df,
    rater_id
):

    if submissions_df.empty:

        return pd.DataFrame()


    if (
        "rater_id"
        not in submissions_df.columns
    ):

        return pd.DataFrame()


    return submissions_df[

        submissions_df[
            "rater_id"
        ].astype(str)

        == str(rater_id)

    ]


def get_completed_questions(
    submissions_df,
    rater_id
):

    rater_data = (
        get_rater_submissions(
            submissions_df,
            rater_id
        )
    )


    if rater_data.empty:

        return set()


    if (
        "question_id"
        not in rater_data.columns
    ):

        return set()


    return set(

        rater_data[
            "question_id"
        ].astype(str).tolist()

    )


def reset_question_form():

    keys_to_remove = [

        "teacher_answer",

        "accuracy",
        "bloom_align",
        "clarity",
        "distractor",
        "curriculum",
        "overall",

        "decision",

        "reason_codes",

        "correction",

        "confirm_defaults",

    ]


    for key in keys_to_remove:

        if key in st.session_state:

            del st.session_state[key]


# ============================================================
# SESSION STATE
# ============================================================

if "selected_question" not in st.session_state:

    st.session_state.selected_question = None


if "submitted_question" not in st.session_state:

    st.session_state.submitted_question = None


if "submitted_result" not in st.session_state:

    st.session_state.submitted_result = None


if "reveal_answer" not in st.session_state:

    st.session_state.reveal_answer = False


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "📝 MCQ Validation Study"
)


st.sidebar.markdown(
    "---"
)


# ============================================================
# RATER IDENTIFICATION
# ============================================================

rater_id = st.sidebar.selectbox(

    "Rater ID",

    options=[
        ""
    ]
    + list(APPROVED_RATERS.keys()),

    format_func=lambda value:

        "Select your Rater ID"

        if value == ""

        else (
            f"{value} — "
            f"{APPROVED_RATERS[value]}"
        )

)


# ============================================================
# SCHOOL
# ============================================================

school = st.sidebar.text_input(

    "School / Institution",

    placeholder=(
        "Enter your school or institution"
    )

)


# ============================================================
# MODE
# ============================================================

mode_options = [

    "📝 Validate Questions"

]


admin_password = None


try:

    admin_password = st.secrets.get(
        "ADMIN_PASSWORD",
        None
    )

except Exception:

    pass


if admin_password:

    mode_options.append(
        "🔐 Admin Dashboard"
    )


mode = st.sidebar.radio(

    "Mode",

    mode_options

)


# ============================================================
# TEACHER VALIDATION MODE
# ============================================================

if mode == "📝 Validate Questions":


    # ========================================================
    # HEADER
    # ========================================================

    st.title(
        "MCQ Validation Study"
    )


    st.markdown(

        """
        Please independently review each multiple-choice question.

        **Workflow:**  
        **Step 1:** Select the answer you believe is correct  
        → **Step 2:** Evaluate the item  
        → **Step 3:** Submit your decision

        The official answer and explanation will only become
        available after your evaluation has been submitted.
        """

    )


    # ========================================================
    # REQUIRE RATER
    # ========================================================

    if not rater_id:

        st.info(

            "Please select your Rater ID "
            "from the sidebar to begin."

        )

        st.stop()


    # ========================================================
    # REQUIRE SCHOOL
    # ========================================================

    if not school.strip():

        st.info(

            "Please enter your School / Institution "
            "in the sidebar to begin."

        )

        st.stop()


    # ========================================================
    # LOAD EXISTING DATA
    # ========================================================

    submissions_df = (
        fetch_submissions()
    )


    completed_questions = (
        get_completed_questions(
            submissions_df,
            rater_id
        )
    )


    all_question_ids = (
        questions_df["ID"]
        .astype(str)
        .tolist()
    )


    remaining_questions = [

        question_id

        for question_id
        in all_question_ids

        if question_id
        not in completed_questions

    ]


    total_questions = len(
        all_question_ids
    )


    completed_count = len(
        completed_questions
    )


    remaining_count = len(
        remaining_questions
    )


    # ========================================================
    # PROGRESS
    # ========================================================

    st.markdown("---")


    progress = (

        completed_count
        / total_questions

        if total_questions > 0

        else 0

    )


    progress_col1, progress_col2 = (
        st.columns([5, 1])
    )


    with progress_col1:

        st.progress(progress)


    with progress_col2:

        st.metric(

            "Progress",

            f"{completed_count}/{total_questions}"

        )


    st.caption(

        f"{completed_count} completed "
        f"· {remaining_count} remaining"

    )


    # ========================================================
    # ALL COMPLETED
    # ========================================================

    if not remaining_questions:

        st.success(

            "You have completed all available "
            "questions. Thank you for your participation."

        )

        st.stop()


    # ========================================================
    # SELECT CURRENT QUESTION
    # ========================================================

    if (

        st.session_state.selected_question
        not in remaining_questions

    ):

        st.session_state.selected_question = (
            remaining_questions[0]
        )


    selected_q = (
        st.session_state.selected_question
    )


    q_row = get_question_row(
        selected_q
    )


    question_number = (

        all_question_ids.index(
            selected_q
        )

        + 1

    )


    # ========================================================
    # QUESTION HEADER
    # ========================================================

    st.markdown("---")


    st.subheader(

        f"Question {question_number} "
        f"of {total_questions}"

    )


    # ========================================================
    # POST-SUBMISSION VIEW
    # ========================================================

    if (

        st.session_state.submitted_question
        == selected_q

        and
        st.session_state.submitted_result
        is not None

    ):


        result = (
            st.session_state.submitted_result
        )


        st.success(
            "Your evaluation has been recorded."
        )


        st.markdown(

            f"**Your Answer:** "
            f"`{result['teacher_answer']}`"

        )


        # ----------------------------------------------------
        # REVEAL ANSWER
        # ----------------------------------------------------

        if not st.session_state.reveal_answer:


            if st.button(

                "Reveal Answer & Explanation"

            ):

                st.session_state.reveal_answer = True

                st.rerun()


        # ----------------------------------------------------
        # DISPLAY ANSWER AFTER REVEAL
        # ----------------------------------------------------

        if st.session_state.reveal_answer:


            st.markdown("---")


            st.subheader(
                "Answer & Explanation"
            )


            st.markdown(

                f"**Recorded Answer Key:** "
                f"`{result['answer_key']}`"

            )


            if (

                result[
                    "answer_agreement"
                ]
                == "AGREE"

            ):

                st.success(

                    "Your answer matches "
                    "the recorded answer key."

                )


            elif (

                result[
                    "answer_agreement"
                ]
                == "DISAGREE"

            ):

                st.warning(

                    "Your answer does not match "
                    "the recorded answer key."

                )


            else:

                st.info(

                    "You selected Unsure."

                )


            st.markdown(
                "**Explanation:**"
            )


            render_text_with_code(
                q_row["Explanation"]
            )


        # ----------------------------------------------------
        # NEXT QUESTION
        # ----------------------------------------------------

        st.markdown("---")


        _, next_col = st.columns(
            [3, 2]
        )


        with next_col:


            if st.button(

                "Next Unrated Question →",

                type="primary",

                use_container_width=True

            ):


                st.cache_data.clear()


                fresh_submissions = (
                    fetch_submissions()
                )


                completed_questions = (
                    get_completed_questions(

                        fresh_submissions,

                        rater_id

                    )
                )


                new_remaining = [

                    question_id

                    for question_id
                    in all_question_ids

                    if question_id
                    not in completed_questions

                ]


                if new_remaining:

                    st.session_state.selected_question = (
                        new_remaining[0]
                    )


                    st.session_state.submitted_question = (
                        None
                    )


                    st.session_state.submitted_result = (
                        None
                    )


                    st.session_state.reveal_answer = (
                        False
                    )


                    reset_question_form()


                    st.rerun()


                else:

                    st.success(
                        "All questions completed."
                    )


        st.stop()


    # ========================================================
    # QUESTION CARD
    # ========================================================

    with st.container(border=True):

        render_text_with_code(
            q_row["Question"]
        )


    # ========================================================
    # OPTIONS
    # ========================================================

    st.markdown(
        "### Answer Options"
    )


    options = {

        "A": q_row["A"],
        "B": q_row["B"],
        "C": q_row["C"],
        "D": q_row["D"],

    }


    option_labels = []


    answer_lookup = {}


    for letter, option_text in options.items():

        label = f"{letter}"


        option_labels.append(
            label
        )


        answer_lookup[label] = letter


    # ========================================================
    # STEP 1
    # ========================================================

    st.markdown("---")


    st.subheader(
        "Step 1 — Your Independent Answer"
    )


    st.caption(

        "First select the answer you believe "
        "is correct."

    )


    selected_answer = st.radio(

        "Your Answer",

        options=[
            "A",
            "B",
            "C",
            "D",
            "Unsure"
        ],

        index=None,

        horizontal=True,

        key="teacher_answer"

    )


    # Display options clearly

    for letter, option_text in options.items():

        with st.container(border=True):

            st.markdown(
                f"**{letter}.**"
            )


            render_text_with_code(
                option_text
            )


    # ========================================================
    # STEP 2
    # ========================================================

    st.markdown("---")


    st.subheader(
        "Step 2 — Item Evaluation"
    )


    st.caption(

        "Rating guide: "
        "**1 = Poor · 2 = Weak · "
        "3 = Acceptable · 4 = Good · "
        "5 = Excellent**"

    )


    rating_col1, rating_col2 = (
        st.columns(2)
    )


    with rating_col1:


        tech_accuracy = st.slider(

            "Technical Accuracy",

            min_value=1,

            max_value=5,

            value=3,

            key="accuracy",

            help=(
                "Is the question, answer structure, "
                "and underlying content technically sound?"
            )

        )


        bloom_align = st.slider(

            "Cognitive-Level Appropriateness",

            min_value=1,

            max_value=5,

            value=3,

            key="bloom_align",

            help=(
                "Does the question appear to require "
                "an appropriate level of cognitive processing?"
            )

        )


        clarity = st.slider(

            "Question Clarity",

            min_value=1,

            max_value=5,

            value=3,

            key="clarity",

            help=(
                "Is the wording clear and unambiguous?"
            )

        )


    with rating_col2:


        distractor = st.slider(

            "Distractor Quality",

            min_value=1,

            max_value=5,

            value=3,

            key="distractor",

            help=(
                "Are the incorrect options plausible "
                "and meaningful?"
            )

        )


        curriculum = st.slider(

            "Curriculum Fit",

            min_value=1,

            max_value=5,

            value=3,

            key="curriculum",

            help=(
                "Is the item relevant to the intended "
                "curriculum?"
            )

        )


        overall = st.slider(

            "Overall Suitability",

            min_value=1,

            max_value=5,

            value=3,

            key="overall",

            help=(
                "Overall suitability of the item "
                "for the intended assessment."
            )

        )


    # ========================================================
    # STEP 3
    # ========================================================

    st.markdown("---")


    st.subheader(
        "Step 3 — Final Decision"
    )


    decision = st.selectbox(

        "Select your decision",

        options=[
            "",
            "ACCEPT",
            "REVISE",
            "REJECT"
        ],

        format_func=lambda value:

            "Select a decision..."

            if value == ""

            else value.title(),

        key="decision"

    )


    # ========================================================
    # REASON CODES
    # ========================================================

    selected_reasons = []


    if decision in [
        "REVISE",
        "REJECT"
    ]:


        st.markdown(
            "#### Issue / Reason Codes"
        )


        st.caption(
            "Select all that apply."
        )


        selected_reasons = (
            st.multiselect(

                "Issue Type(s)",

                options=list(
                    REASON_CODES.keys()
                ),

                format_func=lambda value:

                    (
                        f"{value} — "
                        f"{REASON_CODES[value]}"
                    ),

                key="reason_codes"

            )
        )


    # ========================================================
    # COMMENTS
    # ========================================================

    correction = st.text_area(

        "Suggested Correction / Comments",

        placeholder=(
            "Optional: Describe the problem "
            "or suggest an improvement."
        ),

        key="correction"

    )


    # ========================================================
    # DEFAULT RATING CHECK
    # ========================================================

    ratings = [

        tech_accuracy,
        bloom_align,
        clarity,
        distractor,
        curriculum,
        overall,

    ]


    all_default = all(

        rating == 3

        for rating in ratings

    )


    if all_default:


        confirm_defaults = st.checkbox(

            "I confirm that leaving all six ratings "
            "at 3 reflects my independent judgment.",

            key="confirm_defaults"

        )


    else:

        confirm_defaults = True


    # ========================================================
    # SUBMIT BUTTON
    # ========================================================

    st.markdown("---")


    submit_disabled = (

        selected_answer is None

        or decision == ""

        or not confirm_defaults

    )


    submit_clicked = st.button(

        "Submit Independent Evaluation",

        type="primary",

        use_container_width=True,

        disabled=submit_disabled

    )


    # ========================================================
    # SUBMISSION
    # ========================================================

    if submit_clicked:


        # ----------------------------------------------------
        # FRESH DUPLICATE CHECK
        # ----------------------------------------------------

        fresh_submissions = (
            fetch_submissions()
        )


        completed_now = (
            get_completed_questions(

                fresh_submissions,

                rater_id

            )
        )


        if selected_q in completed_now:


            st.error(

                "This question has already been "
                "submitted under this Rater ID."

            )


            st.stop()


        # ----------------------------------------------------
        # TEACHER ANSWER
        # ----------------------------------------------------

        if selected_answer == "Unsure":

            teacher_answer = "UNSURE"

        else:

            teacher_answer = selected_answer


        # ----------------------------------------------------
        # ANSWER KEY
        # ----------------------------------------------------

        answer_key = str(
            q_row["Answer"]
        ).strip()


        # ----------------------------------------------------
        # AGREEMENT
        # ----------------------------------------------------

        if teacher_answer == "UNSURE":

            answer_agreement = "UNSURE"


        elif teacher_answer == answer_key:

            answer_agreement = "AGREE"


        else:

            answer_agreement = "DISAGREE"


        # ----------------------------------------------------
        # CREATE SUBMISSION
        # ----------------------------------------------------

        submission_dict = {


            "timestamp":

                datetime.now().isoformat(),


            "rater_id":

                rater_id,


            "rater_name":

                APPROVED_RATERS[
                    rater_id
                ],


            "school":

                school.strip(),


            "question_id":

                selected_q,


            # Research metadata

            "topic":

                q_row["Topic"],


            "question_type":

                q_row[
                    "Question Type"
                ],


            "bloom":

                q_row["Bloom"],


            # Independent answer

            "teacher_answer":

                teacher_answer,


            "answer_key":

                answer_key,


            "answer_agreement":

                answer_agreement,


            # Ratings

            "accuracy":

                tech_accuracy,


            "bloom_align":

                bloom_align,


            "clarity":

                clarity,


            "distractor":

                distractor,


            "curriculum":

                curriculum,


            "overall":

                overall,


            # Decision

            "decision":

                decision,


            # Issues

            "reasons":

                " | ".join(
                    selected_reasons
                ),


            "correction":

                correction,

        }


        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        success, message = (
            save_submission(
                submission_dict
            )
        )


        if success:


            st.cache_data.clear()


            st.session_state.submitted_question = (
                selected_q
            )


            st.session_state.submitted_result = {

                "teacher_answer":

                    teacher_answer,


                "answer_key":

                    answer_key,


                "answer_agreement":

                    answer_agreement,

            }


            st.session_state.reveal_answer = (
                False
            )


            reset_question_form()


            st.rerun()


        else:

            st.error(
                message
            )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

elif mode == "🔐 Admin Dashboard":


    st.title(
        "🔐 Administrator Dashboard"
    )


    entered_password = st.text_input(

        "Administrator Password",

        type="password"

    )


    if entered_password != admin_password:


        st.info(

            "Enter the administrator password "
            "to access validation results."

        )


        st.stop()


    # ========================================================
    # LOAD RESULTS
    # ========================================================

    results_df = fetch_submissions()


    if results_df.empty:


        st.info(
            "No validations submitted yet."
        )


        st.stop()


    # ========================================================
    # CONVERT NUMERIC DATA
    # ========================================================

    for column in RATING_COLUMNS:


        if column in results_df.columns:


            results_df[column] = (
                pd.to_numeric(

                    results_df[column],

                    errors="coerce"

                )
            )


    # ========================================================
    # SUMMARY
    # ========================================================

    st.markdown(
        "## Summary"
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


        question_count = (

            results_df[
                "question_id"
            ].nunique()

            if "question_id"
            in results_df.columns

            else 0

        )


        st.metric(

            "Questions Reviewed",

            question_count

        )


    with col3:


        rater_count = (

            results_df[
                "rater_id"
            ].nunique()

            if "rater_id"
            in results_df.columns

            else 0

        )


        st.metric(

            "Raters Participated",

            rater_count

        )


    with col4:


        if "decision" in results_df.columns:


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

            f"{accept_rate:.0f}%"

        )


    # ========================================================
    # ANSWER AGREEMENT
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Answer-Key Agreement"
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


    st.markdown(
        "## Average Ratings"
    )


    available_ratings = [

        column

        for column
        in RATING_COLUMNS

        if column
        in results_df.columns

    ]


    if available_ratings:


        average_ratings = (

            results_df[
                available_ratings
            ]

            .mean()

            .round(2)

            .reset_index()

        )


        average_ratings.columns = [

            "Criterion",

            "Average Score"

        ]


        st.dataframe(

            average_ratings,

            use_container_width=True

        )


        st.bar_chart(

            average_ratings.set_index(
                "Criterion"
            )

        )


    # ========================================================
    # DECISION DISTRIBUTION
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Decision Distribution"
    )


    if "decision" in results_df.columns:


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


        st.bar_chart(

            decision_counts.set_index(
                "Decision"
            )

        )


    # ========================================================
    # PER QUESTION SUMMARY
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Per-Question Breakdown"
    )


    if available_ratings:


        question_summary = (

            results_df

            .groupby(
                "question_id"
            )

            [available_ratings]

            .mean()

            .round(2)

        )


        st.dataframe(

            question_summary,

            use_container_width=True

        )


    # ========================================================
    # REASON CODE ANALYSIS
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Issue / Reason Code Analysis"
    )


    if "reasons" in results_df.columns:


        all_reasons = []


        for reason_text in (

            results_df[
                "reasons"
            ]

            .dropna()

        ):


            reason_list = [

                item.strip()

                for item
                in str(reason_text).split("|")

                if item.strip()

            ]


            all_reasons.extend(
                reason_list
            )


        if all_reasons:


            reason_counts = (

                pd.Series(
                    all_reasons
                )

                .value_counts()

                .reset_index()

            )


            reason_counts.columns = [

                "Reason Code",

                "Count"

            ]


            st.dataframe(

                reason_counts,

                use_container_width=True

            )


            st.bar_chart(

                reason_counts.set_index(
                    "Reason Code"
                )

            )


        else:


            st.info(
                "No reason codes recorded yet."
            )


    # ========================================================
    # RAW DATA
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Raw Validation Data"
    )


    st.dataframe(

        results_df,

        use_container_width=True

    )


    # ========================================================
    # CSV EXPORT
    # ========================================================

    st.markdown("---")


    st.markdown(
        "## Export"
    )


    csv_data = (

        results_df

        .to_csv(
            index=False
        )

        .encode("utf-8")

    )


    st.download_button(

        "⬇️ Download Validation CSV",

        csv_data,

        "rp1_validation_results.csv",

        "text/csv",

        use_container_width=True

    )
