from flask import Flask, request, jsonify
from flask_cors import CORS
from ortools.sat.python import cp_model
from datetime import datetime
import sqlite3

app = Flask(__name__)
CORS(app)

DB_NAME = "schedule.db"

# Helper function to initialize the database and tables if they do not exist
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table for saving finalized and approved schedules
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS past_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day_name TEXT,
            shift_name TEXT,
            hours TEXT,
            employee_name TEXT,
            rank INTEGER,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def parse_time(time_str):
    return datetime.strptime(time_str, "%H:%M").time()

def is_overlapping(start1, end1, start2, end2):
    s1, e1 = parse_time(start1), parse_time(end1)
    s2, e2 = parse_time(start2), parse_time(end2)
    if e1 < s1:
        return s2 >= s1 or s2 <= e1 or e2 >= s1 or e2 <= e1
    if e2 < s2:
        return s1 >= s2 or s1 <= e2 or e1 >= s2 or e1 <= e2
    return max(s1, s2) < min(e1, e2)

# Endpoint: Save the approved schedule to the database for future continuity
@app.route('/api/save_schedule', methods=['POST'])
def save_schedule():
    content = request.json
    final_schedule = content.get('schedule', [])
    
    if not final_schedule:
        return jsonify({"status": "error", "message": "Empty schedule received."}), 400
        
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # For simplicity, we clear the previous schedule so only the latest approved schedule acts as history
        cursor.execute("DELETE FROM past_schedules")
        
        for item in final_schedule:
            day = item.get('Day')
            shift = item.get('ShiftName')
            hours = item.get('Hours')
            staff = item.get('Staff', [])
            
            for person in staff:
                cursor.execute('''
                    INSERT INTO past_schedules (day_name, shift_name, hours, employee_name, rank)
                    VALUES (?, ?, ?, ?, ?)
                ''', (day, shift, hours, person['name'], person['rank']))
                
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Schedule successfully locked and saved to DB."})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Database error: {str(e)}"}), 500


@app.route('/api/schedule', methods=['POST'])
def generate_schedule():
    content = request.json
    days_horizon = content.get('days_horizon', 7)
    max_shifts = content.get('max_shifts_per_employee', 5)
    min_shifts = content.get('min_shifts_per_week', 2)
    strategy = content.get('optimization_strategy', 'fairness')
    active_shifts = content.get('active_shifts', [])
    seed = content.get('seed', 1)
    employees_list = content.get('employees_list', [])
    history_config = content.get('history', {})
    
    if not active_shifts:
        return jsonify({"status": "error", "message": "No active shifts selected."}), 400
    if not employees_list:
        return jsonify({"status": "error", "message": "Employee list is empty."}), 400

    model = cp_model.CpModel()
    num_days = days_horizon
    num_employees = len(employees_list)
    
    # Decision Variables
    shift_vars = {}
    for e in range(num_employees):
        for d in range(num_days):
            for s_idx, shift in enumerate(active_shifts):
                shift_vars[(e, d, s_idx)] = model.NewBoolVar(f'shift_e{e}_d{d}_s{s_idx}')

    # Constraint 1: Exact staff count required per shift
    for d in range(num_days):
        for s_idx, shift in enumerate(active_shifts):
            required_count = shift.get('count', 1)
            model.Add(sum(shift_vars[(e, d, s_idx)] for e in range(num_employees)) == required_count)

    # Constraint 2: Mandatory presence of a Team Lead (rank == 3) if required by the shift
    for d in range(num_days):
        for s_idx, shift in enumerate(active_shifts):
            if shift.get('require_team_lead', False):
                model.Add(sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) if employees_list[e]['rank'] == 3) >= 1)

    # Constraint 3: Mandatory presence of a Senior Researcher or above (rank >= 2) if required
    for d in range(num_days):
        for s_idx, shift in enumerate(active_shifts):
            if shift.get('require_senior', False):
                model.Add(sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) if employees_list[e]['rank'] >= 2) >= 1)

    # Smart History Logic: Retrieve previous night shift workers to enforce rest rules on Day 0
    blocked_for_first_morning = []
    
    if history_config.get('use_db', True):
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT employee_name FROM past_schedules WHERE shift_name LIKE '%לילה%'")
            rows = cursor.fetchall()
            blocked_for_first_morning = [r[0] for r in rows]
            conn.close()
        except:
            pass
    else:
        manual_worker = history_config.get('manual_last_night_worker', '')
        if manual_worker:
            blocked_for_first_morning.append(manual_worker.strip())

    # Historical Hard Constraint: Block morning shifts on Day 1 for employees who worked the previous night shift
    for worker_name in blocked_for_first_morning:
        for e in range(num_employees):
            if employees_list[e]['name'].lower() == worker_name.lower():
                for s_idx, shift in enumerate(active_shifts):
                    start_hour = int(shift['start_hour'].split(':')[0])
                    if start_hour < 12: # Any shift starting before 12:00 PM
                        model.Add(shift_vars[(e, 0, s_idx)] == 0)

    # Constraint 4: Prevent overlapping shifts for the same employee on the same day
    for d in range(num_days):
        for e in range(num_employees):
            for s1_idx, shift1 in enumerate(active_shifts):
                for s2_idx, shift2 in enumerate(active_shifts):
                    if s1_idx < s2_idx:
                        if is_overlapping(shift1['start_hour'], shift1['end_hour'], shift2['start_hour'], shift2['end_hour']):
                            model.Add(shift_vars[(e, d, s1_idx)] + shift_vars[(e, d, s2_idx)] <= 1)

    # Constraint 5: Mandatory rest after a night shift within the current scheduling horizon
    for d in range(num_days - 1):
        for e in range(num_employees):
            for s1_idx, shift1 in enumerate(active_shifts):
                if 'לילה' in shift1['name']:
                    for s2_idx, shift2 in enumerate(active_shifts):
                        start_hour_next_day = int(shift2['start_hour'].split(':')[0])
                        if start_hour_next_day < 12:
                            model.Add(shift_vars[(e, d, s1_idx)] + shift_vars[(e, d+1, s2_idx)] <= 1)

    # Constraint 6: Weekly quotas (Minimum and Maximum shifts per employee)
    for e in range(num_employees):
        first_week_shifts = sum(shift_vars[(e, d, s_idx)] for d in range(min(7, num_days)) for s_idx in range(len(active_shifts)))
        model.Add(first_week_shifts <= max_shifts)
        model.Add(first_week_shifts >= min_shifts)
        
        if num_days > 7:
            second_week_shifts = sum(shift_vars[(e, d, s_idx)] for d in range(7, min(14, num_days)) for s_idx in range(len(active_shifts)))
            model.Add(second_week_shifts <= max_shifts)
            model.Add(second_week_shifts >= min_shifts)

    # Soft Constraints (Penalties and Bonuses for Optimization)
    penalties = []
    bonuses = []

    for d in range(num_days):
        for s_idx, shift in enumerate(active_shifts):
            num_leads = sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) if employees_list[e]['rank'] == 3)
            num_seniors = sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) if employees_list[e]['rank'] == 2)

            # Optimization for Team Leads (Rank 3)
            if shift.get('require_team_lead', False):
                excess_leads = model.NewIntVar(0, num_employees, f'excess_leads_d{d}_s{s_idx}')
                model.Add(excess_leads == num_leads - 1)
                penalties.append(excess_leads * 30)
            else:
                penalties.append(num_leads * 20)

            # Optimization for Senior Researchers (Rank 2) - Prevent unnecessary grouping of experienced staff
            if shift.get('require_senior', False):
                total_experienced = sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) if employees_list[e]['rank'] >= 2)
                excess_exp = model.NewIntVar(0, num_employees, f'excess_exp_d{d}_s{s_idx}')
                model.Add(excess_exp == total_experienced - 1)
                penalties.append(excess_exp * 25)
            else:
                penalties.append(num_seniors * 15) # Penalty for wasting senior staff on non-critical shifts

    # Strategy Modifiers
    if strategy == 'continuity':
        for e in range(num_employees):
            for d in range(num_days - 1):
                for s_idx in range(len(active_shifts)):
                    consec_var = model.NewBoolVar(f'consec_e{e}_d{d}_s{s_idx}')
                    model.Add(consec_var <= shift_vars[(e, d, s_idx)])
                    model.Add(consec_var <= shift_vars[(e, d+1, s_idx)])
                    bonuses.append(consec_var * 50)
                    
    elif strategy == 'balance':
        total_assigned = sum(shift_vars[(e, d, s_idx)] for e in range(num_employees) for d in range(num_days) for s_idx in range(len(active_shifts)))
        penalties.append(total_assigned * 10)

    # Maximize Objective Function
    model.Maximize(sum(bonuses) - sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 5.0
    solver.parameters.random_seed = seed
    
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        generated_schedule = []
        for d in range(num_days):
            day_name = f"יום {d + 1}"
            for s_idx, shift in enumerate(active_shifts):
                staff_assigned = []
                for e in range(num_employees):
                    if solver.Value(shift_vars[(e, d, s_idx)]) == 1:
                        staff_assigned.append({
                            "name": employees_list[e]["name"],
                            "rank": employees_list[e]["rank"]
                        })
                generated_schedule.append({
                    "Day": day_name,
                    "ShiftName": shift['name'],
                    "Hours": f"{shift['start_hour']} - {shift['end_hour']}",
                    "Staff": staff_assigned
                })
        return jsonify({"status": "success", "schedule": generated_schedule})
    else:
        return jsonify({"status": "error", "message": "No feasible solution found for the given constraints."})

if __name__ == '__main__':
    # host='0.0.0.0' allows external devices on the same network to access the server
    app.run(debug=True, host='0.0.0.0', port=5000)