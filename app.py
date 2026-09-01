# app.py
import os
import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

st.write("🔍 Secret keys visible:", list(st.secrets.keys()))
st.write("🔍 sheet_id =", st.secrets.get("sheet_id", "NOT FOUND"))

# ─── PAGE CONFIG ───
st.set_page_config(page_title="MCQ Validation Portal", page_icon="📝", layout="wide")

# ─── LOAD MCQ DATA ───
@st.cache_data
def load_questions():
    df = pd.read_csv("mcq_repository.csv")
    return df

questions_df = load_questions()

# ─── GOOGLE SHEETS CONNECTION ───
def init_sheet():
    creds_json = st.secrets["gcp_service_account"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["sheet_id"]).sheet1

# ─── FETCH EXISTING SUBMISSIONS ───
@st.cache_data(ttl=60)
def fetch_submissions():
    """
    Returns a DataFrame of all existing submissions.
    Handles empty sheets, missing columns, and connection failures.
    Always returns a DataFrame (possibly empty). Never crashes.
    """
    # 1. Try Google Sheets
    try:
        sheet = init_sheet()
        data = sheet.get_all_records()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df
    except Exception:
        pass

    # 2. Try local backup CSV
    try:
        if os.path.exists("validations_backup.csv"):
            df = pd.read_csv("validations_backup.csv")
            df.columns = [str(c).strip().lower() for c in df.columns]
            return df
    except Exception:
        pass

    # 3. Give up gracefully
    return pd.DataFrame()


# ─── SESSION STATE ───
if "teacher_name" not in st.session_state:
    st.session_state.teacher_name = ""
if "force_new" not in st.session_state:
    st.session_state.force_new = False

# ─── SIDEBAR ───
st.sidebar.title("🔐 Teacher Portal")
teacher_name = st.sidebar.text_input("Enter your name", value=st.session_state.teacher_name)
mode = st.sidebar.radio("Select Mode", ["📝 Validate Questions", "📊 View Results"])

if teacher_name:
    st.session_state.teacher_name = teacher_name
else:
    st.sidebar.warning("Please enter your name to continue.")

# ═══════════════════════════════════════════
# MODE 1: VALIDATE QUESTIONS
# ═══════════════════════════════════════════
if mode == "📝 Validate Questions":
    st.title("📝 MCQ Validation Portal")
    st.markdown(f"### Welcome, **{teacher_name}**!")

    # Question selector
    q_ids = questions_df["ID"].tolist()
    selected_q = st.selectbox("Select Question ID", q_ids)
    q_row = questions_df[questions_df["ID"] == selected_q].iloc[0]

    # ─── DUPLICATE CHECK ───
    prior = pd.DataFrame()
    if teacher_name:
        existing = fetch_submissions()
        if not existing.empty and "teacher" in existing.columns and "question_id" in existing.columns:
            prior = existing[
                (existing["teacher"] == teacher_name) &
                (existing["question_id"] == selected_q)
            ]

    editing_allowed = st.session_state.force_new

    if not prior.empty and not editing_allowed:
        st.warning(f"⚠️ You have already validated **{selected_q}**. Showing your prior review below.")
        prev = prior.iloc[-1]
        st.markdown(
            f"**Your prior submission** ({prev.get('timestamp', 'n/a')}):  \n"
            f"- Decision: **{prev.get('decision', '—')}**  \n"
            f"- Accuracy: {prev.get('accuracy', '—')} · Bloom: {prev.get('bloom_align', '—')} · "
            f"Clarity: {prev.get('clarity', '—')} · Distractor: {prev.get('distractor', '—')} · "
            f"Curriculum: {prev.get('curriculum', '—')} · Overall: {prev.get('overall', '—')}  \n"
            f"- Reasons: {prev.get('reasons', '—')}  \n"
            f"- Correction: {prev.get('correction', '—')}"
        )
        if st.button("🔄 Edit / re-submit this question"):
            st.session_state.force_new = True
            st.rerun()
        st.stop()

    if editing_allowed:
        st.info("You are editing an existing submission — a new row will be recorded with a later timestamp.")
        if st.button("↩️ Cancel edit"):
            st.session_state.force_new = False
            st.rerun()

    # ─── DISPLAY QUESTION ───
    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Topic", q_row["Topic"])
    with col2:
        st.metric("Question Type", q_row["Question Type"])
    with col3:
        st.metric("Bloom Level", q_row["Bloom"])

    st.markdown(f"**Question ({selected_q}):** {q_row['Question']}")

    st.markdown("**Options:**")
    options = {"A": q_row["A"], "B": q_row["B"], "C": q_row["C"], "D": q_row["D"]}
    for key, val in options.items():
        marker = " ✅" if key == q_row["Answer"] else ""
        st.markdown(f"- **{key}.** {val}{marker}")

    st.markdown(f"**Recorded Answer:** {q_row['Answer']}")
    st.info(f"**Explanation:** {q_row['Explanation']}")
    if pd.notna(q_row["Validation"]):
        st.warning(f"**Existing Flag:** {q_row['Validation']}")

    # ─── EVALUATION FORM ───
    st.markdown("---")
    st.subheader("📋 Evaluation Form")

    col_a, col_b = st.columns(2)
    with col_a:
        tech_accuracy = st.slider("Technical Accuracy", 1, 5, 3,
                                  help="Is the answer correct? Is the explanation accurate?")
        bloom_align = st.slider("Bloom Alignment", 1, 5, 3,
                                help="Does the cognitive level match the Bloom category?")
        clarity = st.slider("Question Clarity", 1, 5, 3,
                            help="Is the question unambiguous?")
    with col_b:
        distractor = st.slider("Distractor Quality", 1, 5, 3,
                               help="Are wrong answers plausible?")
        curriculum = st.slider("Curriculum Fit", 1, 5, 3,
                               help="Is this relevant to the curriculum?")
        overall = st.slider("Overall Suitability", 1, 5, 3,
                            help="Holistic assessment")

    # ─── DECISION ───
    st.markdown("---")
    decision = st.radio("Decision", ["✅ Accept", "⚠️ Revise", "❌ Reject"], horizontal=True)

    selected_reasons = []
    if decision != "✅ Accept":
        st.markdown("#### Reason Codes (select all that apply)")
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            if st.checkbox("Wrong answer key"): selected_reasons.append("Wrong answer key")
            if st.checkbox("Explanation error"): selected_reasons.append("Explanation error")
            if st.checkbox("Bloom misclassification"): selected_reasons.append("Bloom misclassification")
        with col_r2:
            if st.checkbox("Ambiguous wording"): selected_reasons.append("Ambiguous wording")
            if st.checkbox("Multiple valid answers"): selected_reasons.append("Multiple valid answers")
            if st.checkbox("Outdated content"): selected_reasons.append("Outdated/incorrect content")
        with col_r3:
            if st.checkbox("Too easy/hard"): selected_reasons.append("Too easy/too hard")
            if st.checkbox("Poor distractors"): selected_reasons.append("Poor distractors")
            if st.checkbox("Other"): selected_reasons.append("Other")

    correction = st.text_area("Suggested Correction", placeholder="Describe the fix needed...")

    # ─── SUBMIT ───
    if st.button("Submit Validation", type="primary"):
        if not teacher_name:
            st.error("Please enter your name in the sidebar.")
        else:
            # Final duplicate guard (bypassed only when editing)
            fresh = fetch_submissions()
            if not st.session_state.force_new and not fresh.empty:
                if "teacher" in fresh.columns and "question_id" in fresh.columns:
                    dup = fresh[
                        (fresh["teacher"] == teacher_name) &
                        (fresh["question_id"] == selected_q)
                    ]
                    if not dup.empty:
                        st.error(f"You have already submitted a validation for {selected_q}. "
                                 "Use 'Edit / re-submit' above if you want to update it.")
                        st.stop()

            submission = [
                datetime.now().isoformat(),
                teacher_name,
                selected_q,
                q_row["Topic"],
                q_row["Bloom"],
                str(tech_accuracy),
                str(bloom_align),
                str(clarity),
                str(distractor),
                str(curriculum),
                str(overall),
                decision,
                " | ".join(selected_reasons),
                correction
            ]

            submission_columns = [
                "timestamp", "teacher", "question_id", "topic", "bloom",
                "accuracy", "bloom_align", "clarity", "distractor",
                "curriculum", "overall", "decision", "reasons", "correction"
            ]

            try:
                sheet = init_sheet()
                sheet.append_row(submission)
                st.session_state.force_new = False
                st.cache_data.clear()
                st.success(f"✅ Validation for {selected_q} submitted successfully!")
                st.balloons()
            except Exception as e:
                st.error(f"Error saving to Google Sheets: {e}")
                st.info("Data saved locally as fallback.")
                try:
                    pd.DataFrame([submission], columns=submission_columns).to_csv(
                        "validations_backup.csv", mode="a", header=False, index=False
                    )
                except Exception as e2:
                    st.error(f"Fallback save also failed: {e2}")

# ═══════════════════════════════════════════
# MODE 2: VIEW RESULTS DASHBOARD
# ═══════════════════════════════════════════
elif mode == "📊 View Results":
    st.title("📊 Validation Results Dashboard")

    results_df = fetch_submissions()

    if results_df.empty:
        st.info("No validations submitted yet.")
        st.stop()

    rating_cols = ["accuracy", "bloom_align", "clarity", "distractor", "curriculum", "overall"]
    for col in rating_cols:
        if col in results_df.columns:
            results_df[col] = pd.to_numeric(results_df[col], errors="coerce")

    st.markdown("### Summary Statistics")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Submissions", len(results_df))
    with col2:
        st.metric("Questions Reviewed", results_df["question_id"].nunique() if "question_id" in results_df.columns else 0)
    with col3:
        st.metric("Teachers Participated", results_df["teacher"].nunique() if "teacher" in results_df.columns else 0)
    with col4:
        if "decision" in results_df.columns:
            accept_rate = (results_df["decision"] == "✅ Accept").mean() * 100
        else:
            accept_rate = 0
        st.metric("Accept Rate", f"{accept_rate:.0f}%")

    st.markdown("### Average Ratings by Criterion")
    available_rating_cols = [c for c in rating_cols if c in results_df.columns]
    if available_rating_cols:
        avg_ratings = results_df[available_rating_cols].mean().reset_index()
        avg_ratings.columns = ["Criterion", "Average Score"]
        import plotly.express as px
        fig = px.bar(avg_ratings, x="Criterion", y="Average Score",
                     range_y=[0, 5], color="Criterion",
                     title="Average Scores Across All Questions")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No rating data found in submissions.")

    st.markdown("### Per-Question Breakdown")
    if "question_id" in results_df.columns and available_rating_cols:
        question_summary = results_df.groupby("question_id")[available_rating_cols].mean()
        st.dataframe(question_summary.style.highlight_low(axis=1, props="color:red"))
    else:
        st.info("Insufficient data for per-question breakdown.")

    st.markdown("### Rejection Pattern Analysis")
    if "decision" in results_df.columns:
        rejected = results_df[results_df["decision"] != "✅ Accept"]
    else:
        rejected = pd.DataFrame()

    if not rejected.empty and "reasons" in rejected.columns:
        all_reasons = []
        for r in rejected["reasons"].dropna():
            all_reasons.extend([x.strip() for x in r.split("|")])
        if all_reasons:
            reason_counts = pd.Series(all_reasons).value_counts()
            import plotly.express as px
            fig2 = px.bar(x=reason_counts.values, y=reason_counts.index,
                          orientation="h", color=reason_counts.values,
                          title="Rejection Reason Frequency",
                          labels={"x": "Count", "y": "Reason"})
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No rejections to analyse yet.")

    st.markdown("### Export Data")
    csv = results_df.to_csv(index=False).encode()
    st.download_button("⬇️ Download CSV", csv, "validations.csv", "text/csv")
