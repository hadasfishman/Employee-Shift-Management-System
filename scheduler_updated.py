import streamlit as st
from ortools.sat.python import cp_model
import pandas as pd
import matplotlib.pyplot as plt

# 1. Data Structures:

class Employee:
    # This class represents a single worker in the organization.
    def __init__(self, name, worker_key, role, level, current_ranking):
        self.name = name 
        self.worker_key = worker_key # Unique identifier (Primary Key for SQL mapping)
        self.role = role.strip()  # Employee role 
        self.level = level # Seniority level (Integer, typically 1-3)
        self.current_ranking = current_ranking # Historical workload ranking used for fairness optimization

class ShiftConfig:
    # this class difined requirments for each shift type
    def __init__(self, name, total_workers, role_requirements):
        self.name = name # shift name # Name of the shift
        self.total_workers = total_workers # Total number of workers required for this shift
        self.role_requirements = role_requirements # Dictionary defining minimum workers per role (e.g., {"Manager": 1})

# 2. The Logic Engine (Deterministic CP-SAT Solver):

def solve_schedule(employees, days, shifts_config, min_shifts, max_shifts, strategy):
    """
    This function uses Google OR-Tools CP-SAT solver to compute an optimal schedule
    based on hard constraints (staffing rules) and soft criteria (fairness and balance).
    """
    # 1. Initialize the CP-SAT Model container
    model = cp_model.CpModel()

    # 2. Dictionary to hold our Decision Variables.
    # Key: (employee_name, day, shift_name) -> Value: CpModel BoolVar (0 or 1)
    shifts = {}

    # 3. Create a 3D grid of binary variables (Every employee x Every day x Every shift)
    for e in employees:
        for d in days:
            for s in shifts_config:
                # The triple loop creates combination of all options.
                # Variable Name format: "shift_Alice_1_Morning"
                # If the solver sets this variable to 1, it means Alice works Morning on Day 1.
                shifts[(e.name, d, s.name)] = model.NewBoolVar(f'shift_{e.name}_{d}_{s.name}')


    # 4. HARD CONSTRAINTS:
    
    # A. Staffing Quantity & Roles
    for d in days:
        for s in shifts_config:
            # 1. Total workers constraint: Gather all variables for this specific day and shift
            workers_in_shift = [shifts[(e.name, d, s.name)] for e in employees]
            # The sum of these variables must equal the required total (e.g., exactly 3 workers)
            model.Add(sum(workers_in_shift) == s.total_workers)
            
            # 2. Specific role constraints (e.g., minimum 1 Manager)
            for role_name, min_count in s.role_requirements.items():
                # Filter only the workers who belong to this specific role
                specific_workers = [shifts[(e.name, d, s.name)] for e in employees if e.role == role_name]
                if specific_workers:
                    # The sum of assigned workers from this role must be greater than or equal to min_count
                    model.Add(sum(specific_workers) >= min_count)

            # 3. Seniority constraint: At least one senior employee (Level >= 2) per shift
            seniors = [shifts[(e.name, d, s.name)] for e in employees if e.level >= 2]
            if seniors:
                model.Add(sum(seniors) >= 1)

    # B. Daily Limit: Max 1 shift per day per employee
    for e in employees:
        for d in days:
            # Gather all variables for this specific employee on this specific day
            daily_shifts = [shifts[(e.name, d, s.name)] for s in shifts_config]
            # An employee can work at most 1 shift per day (0 or 1)
            model.Add(sum(daily_shifts) <= 1)

    # C. Weekly Limits & STRATEGY
    for e in employees:
        weekly_shifts = []
        for d in days:
            for s in shifts_config:
                # Collect every single potential shift for this employee over the whole week
                weekly_shifts.append(shifts[(e.name, d, s.name)])
        
        # Enforce the global min and max weekly shift limits for each employee
        model.Add(sum(weekly_shifts) <= max_shifts)
        model.Add(sum(weekly_shifts) >= min_shifts)
    

    # 5. STRATEGY SETTINGS:
    
    # Define optimization weights based on the user-selected strategy
    if strategy == "Aggressive Catch-up":
        HISTORICAL_WEIGHT = 100 
        BALANCING_WEIGHT = 1    
    else: # Default - Weekly Balance
        HISTORICAL_WEIGHT = 1
        BALANCING_WEIGHT = 10 

        # Check for each worker that the assigned shifts are between min and max per week.
        weekly_shifts = []
        for d in days:
            for s in shifts_config:
                weekly_shifts.append(shifts[(e.name, d, s.name)])
        
        model.Add(sum(weekly_shifts) <= max_shifts)
        model.Add(sum(weekly_shifts) >= min_shifts)

        # 1. SOFT CONSTRAINT 1: Historical Penalty (Fairness based on past ranking)
        for d in days:
            for s in shifts_config:
                objective_terms.append(shifts[(e.name, d, s.name)] * int(e.current_ranking) * HISTORICAL_WEIGHT)

        # 2. SOFT CONSTRAINT 2: Weekly Load Balancing (Mathematical Smoothing using quadratic cost)
        num_shifts_var = model.NewIntVar(0, max_shifts, f'num_shifts_{e.name}')
        model.Add(num_shifts_var == sum(weekly_shifts))
        
        squared_shifts = model.NewIntVar(0, max_shifts**2, f'squared_{e.name}')
        model.AddMultiplicationEquality(squared_shifts, [num_shifts_var, num_shifts_var])
        objective_terms.append(squared_shifts * BALANCING_WEIGHT)

    # 6. MODEL EXECUTION & OUTPUT GENERATION:
    model.Minimize(sum(objective_terms))

    # Initialize the Google OR-Tools constraint satisfaction solver
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # Validate if a mathematically feasible or globally optimal solution was reached
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        employee_shift_counts = {e.name: 0 for e in employees}

        # Parse the multi-dimensional binary matrix back into a human-readable structure
        for d in days:
            day_row = {"Day": d}
            for s in shifts_config:
                assigned = []
                for e in employees:
                    # solver.Value() extracts the final evaluation (0 or 1) of the decision variable
                    if solver.Value(shifts[(e.name, d, s.name)]):
                        assigned.append(f"{e.name} ({e.role})")
                        employee_shift_counts[e.name] += 1
                day_row[s.name] = ", ".join(assigned)
            schedule_data.append(day_row)
        
        # Return a structured Pandas DataFrame for the UI grid, alongside analytics metrics
        return pd.DataFrame(schedule_data), employee_shift_counts
    else:
        # Return empty handles if the current parameter matrix results in an infeasible model
        return None, None


# ##################################################
# --- 3. UI (Streamlit) ---

st.set_page_config(page_title="Smart Scheduler", layout="wide")
st.title("⚖️ Smart Shift Scheduler")

# Sidebar - Data Input
st.sidebar.header("1. Data Upload")

sample_data = pd.DataFrame({
    'Name': ['Alice', 'Bob', 'Charlie', 'David', 'Eve', 'Frank'],
    'Role': ['Support', 'Support', 'Manager', 'Technician', 'Technician', 'Manager'],
    'Level': [1, 1, 3, 2, 2, 3], 
    'Ranking': [0, 5, 2, 4, 1, 6]
})
st.sidebar.download_button("📥 Download Sample Staff CSV", sample_data.to_csv(index=False).encode('utf-8'), "staff_sample.csv")
uploaded_file = st.sidebar.file_uploader("Upload Staff CSV", type=['csv'])

if uploaded_file:
    df = pd.read_csv(uploaded_file)
    employees = [Employee(row['Name'], row['Role'], row['Level'], row['Ranking']) for i, row in df.iterrows()]
    unique_roles = df['Role'].unique().tolist()
    st.sidebar.success(f"Loaded roles: {', '.join(unique_roles)}")

    st.header("1. Optimization Strategy")

    # --- STRATEGY SELECTOR ---
    strategy = st.radio(
        "Select Assignment Strategy:",
        ("⚖️ Weekly Balance (Spread shifts evenly)", "⚡ Aggressive Catch-up (Prioritize fairness over load)"),
        index=0
    )
    
    if strategy.startswith("⚡"):
        st.info("💡 **Mode active:** Employees with lower historical ranks are heavily prioritized for new shifts.")
        strat_key = "Aggressive Catch-up"
    else:
        st.info("💡 **Mode active:** The solver minimizes the variance between team members' weekly workloads.")
        strat_key = "Weekly Balance"

    st.header("2. Horizon & Constraints")
    col1, col2, col3 = st.columns(3)
    with col1: num_days = st.number_input("Scheduling Horizon (Days)", 1, 31, 7)
    with col2: min_shifts = st.number_input("Min Shifts per Employee", 0, 10, 0)
    with col3: max_shifts = st.number_input("Max Shifts per Employee", 1, 14, 7)

    st.markdown("---")
    st.header("3. Shift Configuration")
    
    with st.expander("☀️ Morning Shift Settings", expanded=True):
        m_total = st.number_input("Total Workers Needed (Morning)", 1, 20, 3)
        m_reqs = {}
        cols = st.columns(len(unique_roles))
        for i, role in enumerate(unique_roles):
            with cols[i]:
                val = st.number_input(f"Min {role} (Morning)", 0, 5, 1, key=f"m_{role}")
                if val > 0: m_reqs[role] = val

    with st.expander("🌙 Evening Shift Settings", expanded=True):
        e_total = st.number_input("Total Workers Needed (Evening)", 1, 20, 3)
        e_reqs = {}
        cols = st.columns(len(unique_roles))
        for i, role in enumerate(unique_roles):
            with cols[i]:
                val = st.number_input(f"Min {role} (Evening)", 0, 5, 1, key=f"e_{role}")
                if val > 0: e_reqs[role] = val

    shift_configs = [ShiftConfig("Morning", m_total, m_reqs), ShiftConfig("Evening", e_total, e_reqs)]

    st.markdown("---")
    if st.button("🚀 Run Combinatorial Optimization"):
        with st.spinner("Solving constraints using CP-SAT Engine..."):
            result_df, shift_counts = solve_schedule(employees, range(1, num_days+1), shift_configs, min_shifts, max_shifts, strat_key)
        
        if result_df is not None:
            st.success("Optimal Solution Found!")
            st.table(result_df)
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("### 📊 Current Week Load Distribution")
                fig1, ax1 = plt.subplots()
                active = {k: v for k, v in shift_counts.items() if v > 0}
                vals = list(active.values())
                def make_autopct(values):
                    def my_autopct(pct):
                        total = sum(values)
                        val = int(round(pct*total/100.0))
                        return '{p:.1f}%\n({v:d} shifts)'.format(p=pct, v=val)
                    return my_autopct
                ax1.pie(vals, labels=active.keys(), autopct=make_autopct(vals), startangle=90)
                st.pyplot(fig1)

            with c2:
                st.markdown("### ⚖️ Fairness Tracking (Catch-up Assessment)")
                names = [e.name for e in employees]
                past = [e.current_ranking for e in employees]
                new_s = [shift_counts[e.name] for e in employees]
                fig2, ax2 = plt.subplots()
                ax2.bar(names, past, label='Historical Penalty Rank', color='lightblue')
                ax2.bar(names, new_s, bottom=past, label='Newly Assigned Shifts', color='tomato')
                ax2.legend()
                st.pyplot(fig2)

            # Download Option
            updated_df = df.copy()
            updated_df['Ranking'] = updated_df.apply(lambda r: r['Ranking'] + shift_counts.get(r['Name'], 0), axis=1)
            st.download_button("📥 Export Updated Analytics (CSV)", updated_df.to_csv(index=False).encode('utf-8'), "updated_staff.csv", "text/csv")
        else:
            st.error("🚨 Infeasible Constraints: The engine could not find a valid schedule with the current parameter configurations. Try lowering minimum shift rules or increasing total staff size.")
else:
    st.info("👋 Please upload a valid Staff CSV file in the sidebar to configure and compute the scheduling horizon.")