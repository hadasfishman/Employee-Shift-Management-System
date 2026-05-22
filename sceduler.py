import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import matplotlib.pyplot as plt
import requests  
import json

# --- 1. Data Structures ---

class Employee:
    def __init__(self, name, role, level, current_ranking):
        self.name = name
        self.role = role.strip() 
        self.level = level       
        self.current_ranking = current_ranking

class ShiftConfig:
    def __init__(self, name, total_workers, role_requirements):
        self.name = name
        self.total_workers = total_workers
        self.role_requirements = role_requirements

# --- 2. AI Logic Engine (REST API) ---

def get_ai_config(user_prompt, roles, api_key):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = f"""
    Convert this user request into scheduling parameters. 
    Available roles: {roles}
    Return ONLY a JSON with these exact keys: 
    'm_total' (int), 'e_total' (int), 'strategy' (string: 'Weekly Balance' or 'Aggressive Catch-up'),
    'm_reqs' (dict of role:min_count), 'e_reqs' (dict of role:min_count).
    User request: "{user_prompt}"
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        content = response.json()['candidates'][0]['content']['parts'][0]['text']
        return json.loads(content)
    except Exception as e:
        st.error(f"AI Connection Error: {e}")
        return None

# --- 3. The Logic Engine (Solver) ---

def solve_schedule(employees, days, shifts_config, min_shifts, max_shifts, strategy):
    model = cp_model.CpModel()
    shifts = {}

    # Create Variables
    for e in employees:
        for d in days:
            for s in shifts_config:
                shifts[(e.name, d, s.name)] = model.NewBoolVar(f'shift_{e.name}_{d}_{s.name}')

    # --- HARD CONSTRAINTS ---

    # A. Staffing Quantity & Roles
    for d in days:
        for s in shifts_config:
            workers_in_shift = [shifts[(e.name, d, s.name)] for e in employees]
            model.Add(sum(workers_in_shift) == s.total_workers)
            
            for role_name, min_count in s.role_requirements.items():
                specific_workers = [shifts[(e.name, d, s.name)] for e in employees if e.role == role_name]
                if specific_workers:
                    model.Add(sum(specific_workers) >= min_count)

            seniors = [shifts[(e.name, d, s.name)] for e in employees if e.level >= 2]
            if seniors:
                model.Add(sum(seniors) >= 1)

    # B. Daily Limit
    for e in employees:
        for d in days:
            daily_shifts = [shifts[(e.name, d, s.name)] for s in shifts_config]
            model.Add(sum(daily_shifts) <= 1)

    # C. Weekly Limits & STRATEGY
    objective_terms = []
    
    # --- STRATEGY SETTINGS ---
    if strategy == "Aggressive Catch-up":
        # YOUR REQUEST: Huge penalty for historical rank, almost zero penalty for weekly load.
        # This means: If Rank is high, DON'T schedule. If Rank is low, Schedule A LOT.
        HISTORICAL_WEIGHT = 100 
        BALANCING_WEIGHT = 1    # Tiny weight just to break ties
    else:
        # PREVIOUS MODE: Balance the week nicely.
        HISTORICAL_WEIGHT = 1
        BALANCING_WEIGHT = 10 

    for e in employees:
        weekly_shifts = []
        for d in days:
            for s in shifts_config:
                weekly_shifts.append(shifts[(e.name, d, s.name)])
        
        model.Add(sum(weekly_shifts) <= max_shifts)
        model.Add(sum(weekly_shifts) >= min_shifts)

        # 1. Historical Penalty (The Fairness)
        # "current_ranking" is the cumulative score. High score = High Cost to schedule.
        for d in days:
            for s in shifts_config:
                objective_terms.append(shifts[(e.name, d, s.name)] * int(e.current_ranking) * HISTORICAL_WEIGHT)

        # 2. Weekly Load Balancing (The Smoothing)
        # If Balancing Weight is LOW (your request), the solver won't care if someone works 7 days.
        num_shifts_var = model.NewIntVar(0, max_shifts, f'num_shifts_{e.name}')
        model.Add(num_shifts_var == sum(weekly_shifts))
        
        squared_shifts = model.NewIntVar(0, max_shifts**2, f'squared_{e.name}')
        model.AddMultiplicationEquality(squared_shifts, [num_shifts_var, num_shifts_var])
        objective_terms.append(squared_shifts * BALANCING_WEIGHT)

    # --- SOLVE ---
    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        employee_shift_counts = {e.name: 0 for e in employees}

        for d in days:
            day_row = {"Day": d}
            for s in shifts_config:
                assigned = []
                for e in employees:
                    if solver.Value(shifts[(e.name, d, s.name)]):
                        assigned.append(f"{e.name} ({e.role})")
                        employee_shift_counts[e.name] += 1
                day_row[s.name] = ", ".join(assigned)
            schedule_data.append(day_row)
        
        return pd.DataFrame(schedule_data), employee_shift_counts
    else:
        return None, None

# --- 4. UI ---

st.set_page_config(page_title="Smart Scheduler", layout="wide")
st.title("⚖️ Smart Shift Scheduler")

# Sidebar
st.sidebar.header("1. Data Upload")

sample_data = pd.DataFrame({
    'Name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Frank'],
    'Role': ['Support', 'Support', 'Manager', 'Technician', 'Technician', 'Manager'],
    'Level': [1, 1, 3, 2, 2, 3], 
    'Ranking': [0, 5, 2, 4, 1, 6]
})
st.sidebar.download_button("📥 Sample CSV", sample_data.to_csv(index=False).encode('utf-8'), "staff_sample.csv")
uploaded_file = st.sidebar.file_uploader("Upload Staff CSV", type=['csv'])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    employees = [Employee(row['Name'], row['Role'], row['Level'], row['Ranking']) for i, row in df.iterrows()]
    unique_roles = df['Role'].unique().tolist()
    st.sidebar.success(f"Roles: {', '.join(unique_roles)}")

    # --- AI INTEGRATION ---
    st.markdown("---")
    st.header("🪄 AI Quick Config")
    ai_prompt = st.text_input("Tell the AI how to set up the week (e.g., 'Double staff for morning shifts, prioritize new workers')")

    ai_api_key = "AIzaSyD57H-bNzL1tI_WlzS5VR9E1eQfYhGy3S0"
    
    # default values
    m_total_val, e_total_val = 3, 3
    strat_index = 1 # Aggressive
    m_role_defaults, e_role_defaults = {}, {}

    if ai_prompt and ai_api_key:
        with st.spinner("Gemini is analyzing your request..."):
            config = get_ai_config(ai_prompt, unique_roles, ai_api_key)
            if config:
                m_total_val = config.get('m_total', 3)
                e_total_val = config.get('e_total', 3)
                strat_index = 0 if config.get('strategy') == "Weekly Balance" else 1
                m_role_defaults = config.get('m_reqs', {})
                e_role_defaults = config.get('e_reqs', {})
                st.success("AI updated the settings below!")

    st.header("2. Strategy & Settings")

    # --- STRATEGY SELECTOR ---
    strategy = st.radio(
        "Select Assignment Strategy:",
        ("⚖️ Weekly Balance (Spread shifts evenly)", "⚡ Aggressive Catch-up (Prioritize fairness over load)"),
        index=strat_index # value from ai 
    )
    
    st.header("2. Strategy & Settings")
    
    # # --- STRATEGY SELECTOR ---
    # strategy = st.radio(
    #     "Select Assignment Strategy:",
    #     ("⚖️ Weekly Balance (Spread shifts evenly)", "⚡ Aggressive Catch-up (Prioritize fairness over load)"),
    #     index=1 # Default to Aggressive based on your request
    # )
    
    if strategy.startswith("⚡"):
        st.info("💡 **Mode:** New employees (Low Rank) will work MAX shifts. Veterans will rest.")
        strat_key = "Aggressive Catch-up"
    else:
        st.info("💡 **Mode:** Shifts will be spread as evenly as possible this week.")
        strat_key = "Weekly Balance"

    col1, col2, col3 = st.columns(3)
    with col1: num_days = st.number_input("Days", 1, 31, 7)
    with col2: min_shifts = st.number_input("Min Shifts", 0, 10, 0)
    with col3: max_shifts = st.number_input("Max Shifts", 1, 14, 7)

    st.markdown("---")
    with st.expander("☀️ Morning Config", expanded=True):
        m_total = st.number_input("Total (Morning)", 1, 20, 3)
        m_reqs = {}
        cols = st.columns(len(unique_roles))
        for i, role in enumerate(unique_roles):
            with cols[i]:
                val = st.number_input(f"Min {role}", 0, 5, 1, key=f"m_{role}")
                if val > 0: m_reqs[role] = val

    with st.expander("🌙 Evening Config", expanded=True):
        e_total = st.number_input("Total (Evening)", 1, 20, 3)
        e_reqs = {}
        cols = st.columns(len(unique_roles))
        for i, role in enumerate(unique_roles):
            with cols[i]:
                val = st.number_input(f"Min {role}", 0, 5, 1, key=f"e_{role}")
                if val > 0: e_reqs[role] = val

    shift_configs = [ShiftConfig("Morning", m_total, m_reqs), ShiftConfig("Evening", e_total, e_reqs)]

    if st.button("🚀 Run Scheduler"):
        result_df, shift_counts = solve_schedule(employees, range(1, num_days+1), shift_configs, min_shifts, max_shifts, strat_key)
        
        if result_df is not None:
            st.success("Success!")
            st.table(result_df)
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Weekly Load**")
                fig1, ax1 = plt.subplots()
                active = {k: v for k, v in shift_counts.items() if v > 0}
                vals = list(active.values())
                def make_autopct(values):
                    def my_autopct(pct):
                        total = sum(values)
                        val = int(round(pct*total/100.0))
                        return '{p:.1f}%\n({v:d})'.format(p=pct, v=val)
                    return my_autopct
                ax1.pie(vals, labels=active.keys(), autopct=make_autopct(vals), startangle=90)
                st.pyplot(fig1)

            with c2:
                st.markdown("**Fairness (Catch-up Effect)**")
                names = [e.name for e in employees]
                past = [e.current_ranking for e in employees]
                new_s = [shift_counts[e.name] for e in employees]
                fig2, ax2 = plt.subplots()
                ax2.bar(names, past, label='Past Rank', color='lightblue')
                ax2.bar(names, new_s, bottom=past, label='New Shifts', color='red') # Red = Aggressive load
                ax2.legend()
                st.pyplot(fig2)

            # Download
            updated_df = df.copy()
            updated_df['Ranking'] = updated_df.apply(lambda r: r['Ranking'] + shift_counts.get(r['Name'], 0), axis=1)
            st.download_button("📥 Download Updated CSV", updated_df.to_csv(index=False).encode('utf-8'), "updated_staff.csv", "text/csv")
        else:
            st.error("No solution.")