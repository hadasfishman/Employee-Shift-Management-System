import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from ortools.sat.python import cp_model

# אתחול האפליקציה והגדרת CORS למניעת חסימות דפדפן
app = Flask(__name__)
CORS(app)  

DB_FILE = "scheduler.db"

# =========================================================================
# --- חלק 1: אתחול בסיס הנתונים (SQL Database Setup) ---
# =========================================================================
def init_db():
    """
    Initializes the SQLite relational database and injects initial seed data
    if the employees table is empty.
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # יצירת טבלת העובדים הרלציונית
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            level INTEGER NOT NULL,
            ranking INTEGER NOT NULL
        )
    ''')
    conn.commit()

    # בדיקה אם הטבלה ריקה - הזרקת נתוני האמת של תא המחקר
    cursor.execute("SELECT COUNT(*) FROM employees")
    if cursor.fetchone()[0] == 0:
        sample_staff = [
            # (worker_key, name, role, level, ranking)
            ('MIL001', 'Michal', 'Researcher', 2, 0),    # חוקרת בכירה
            ('MIL002', 'Romy', 'Researcher', 2, 3),      # חוקרת בכירה
            ('MIL003', 'Adi', 'Researcher', 2, 5),       # חוקרת בכירה
            ('MIL004', 'Elhanan', 'Researcher', 1, 1),   # חוקר חדש
            ('MIL005', 'Yoav', 'Researcher', 1, 0),      # חוקר חדש
            ('MIL006', 'Dori', 'Team Lead', 3, 2),       # ראש תא (ר"ת)
            ('MIL007', 'Ofri', 'Team Lead', 3, 4),       # ראש תא (ר"ת)
            ('MIL008', 'Netta', 'Team Lead', 3, 1)       # ראש תא (ר"ת)
        ]
        cursor.executemany(
            "INSERT INTO employees (worker_key, name, role, level, ranking) VALUES (?, ?, ?, ?, ?)", 
            sample_staff
        )
        conn.commit()
    conn.close()


# =========================================================================
# --- חלק 2: מבני הנתונים (Data Structures / OOP) ---
# =========================================================================
class Employee:
    def __init__(self, name, worker_key, role, level, current_ranking):
        self.name = name
        self.worker_key = worker_key
        self.role = role.strip()
        self.level = level
        self.current_ranking = current_ranking

class ShiftConfig:
    def __init__(self, name, total_workers):
        self.name = name
        self.total_workers = total_workers


# =========================================================================
# --- חלק 3: מנוע האופטימיזציה (The CP-SAT Algorithm Engine) ---
# =========================================================================
def solve_schedule(employees, days, min_shifts, max_shifts, strategy):
    """
    Uses Google OR-Tools CP-SAT solver to compute an optimal schedule
    based on the intelligence cell's operational constraints and fairness guidelines.
    """
    model = cp_model.CpModel()
    shifts = {}
    shift_types = ["Day", "Night"]

    # 1. יצירת משתני ההחלטה הבוליאניים (Boolean Decision Variables)
    for e in employees:
        for d in days:
            for s in shift_types:
                shifts[(e.name, d, s)] = model.NewBoolVar(f'shift_{e.name}_{d}_{s}')

    # =========================================================================
    # --- HARD CONSTRAINTS (המגבלות המבצעיות של התא) ---
    # =========================================================================
    for d in days:
        # --- אילוצים עבור משמרת יום (Day Shift) ---
        day_workers = [shifts[(e.name, d, 'Day')] for e in employees]
        model.Add(sum(day_workers) == 3)  # בדיקה שבמשמרת יום יש בדיוק 3 אנשים
        
        # בכל משמרת יום חייב להיות לפחות ראש תא (Team Lead) אחד
        day_leads = [shifts[(e.name, d, 'Day')] for e in employees if e.role == 'Team Lead']
        model.Add(sum(day_leads) >= 1)
        
        # בכל משמרת יום חייב להיות לפחות חוקרת בכירה אחת (רמה 2)
        day_seniors = [shifts[(e.name, d, 'Day')] for e in employees if e.level == 2]
        model.Add(sum(day_seniors) >= 1)

        # --- אילוצים עבור משמרת לילה (Night Shift) ---
        night_workers = [shifts[(e.name, d, 'Night')] for e in employees]
        model.Add(sum(night_workers) == 2)  # בדיקה שבמשמרת לילה יש בדיוק 2 אנשים
        
        # בלילה חייב לפחות נציג אחד מוסמך (רמה 2 ומעלה - ר"ת או חוקרת בכירה)
        night_qualified = [shifts[(e.name, d, 'Night')] for e in employees if e.level >= 2]
        model.Add(sum(night_qualified) >= 1)

    # --- מגבלה יומית: עובד לא יכול לעשות יותר ממשמרת אחת באותו יום ---
    for e in employees:
        for d in days:
            daily_shifts = [shifts[(e.name, d, s)] for s in shift_types]
            model.Add(sum(daily_shifts) <= 1)

    # =========================================================================
    # --- SOFT CONSTRAINTS & STRATEGY OPTIMIZATION ---
    # =========================================================================
    objective_terms = []
    
    if strategy == "Aggressive Catch-up":
        HISTORICAL_WEIGHT = 100 
        BALANCING_WEIGHT = 1    
    else:  # Default: Weekly Balance
        HISTORICAL_WEIGHT = 1
        BALANCING_WEIGHT = 10 

    for e in employees:
        weekly_shifts = []
        for d in days:
            for s in shift_types:
                weekly_shifts.append(shifts[(e.name, d, s)])
        
        # אכיפת המכסות השבועיות (מינימום/מקסימום)
        model.Add(sum(weekly_shifts) <= max_shifts)
        model.Add(sum(weekly_shifts) >= min_shifts)

        # 1. הקנס ההיסטורי לשמירה על הגינות
        for d in days:
            for s in shift_types:
                objective_terms.append(shifts[(e.name, d, s)] * int(e.current_ranking) * HISTORICAL_WEIGHT)

        # 2. איזון עומסים ריבועי (Load Balancing)
        num_shifts_var = model.NewIntVar(0, max_shifts, f'num_shifts_{e.name}')
        model.Add(num_shifts_var == sum(weekly_shifts))
        
        squared_shifts = model.NewIntVar(0, max_shifts**2, f'squared_{e.name}')
        model.AddMultiplicationEquality(squared_shifts, [num_shifts_var, num_shifts_var])
        objective_terms.append(squared_shifts * BALANCING_WEIGHT)

    # הרצת הסולבר
    model.Minimize(sum(objective_terms))
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # עיבוד התוצאות לפורמט מערך (Array) מסודר
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        for d in days:
            day_row = {
                "Day": f"Day {d}",
                "DayShift": "",
                "NightShift": ""
            }
            
            day_assigned = [e.name for e in employees if solver.Value(shifts[(e.name, d, 'Day')])]
            day_row["DayShift"] = ", ".join(day_assigned)
            
            night_assigned = [e.name for e in employees if solver.Value(shifts[(e.name, d, 'Night')])]
            day_row["NightShift"] = ", ".join(night_assigned)  # תיקון השמה כפולה
            
            schedule_data.append(day_row)
        return schedule_data
    return None


# =========================================================================
# --- חלק 4: נתיבי הרשת (Flask REST API Endpoints) ---
# =========================================================================
@app.route('/api/schedule', methods=['POST'])
def get_schedule():
    """
    POST API Endpoint that fetches employee data from SQL, extracts UI configurations,
    triggers the CP-SAT optimization core, and responds with JSON.
    """
    # 1. שליפת הנתונים - תיקון סדר השליפה שיתאים בדיוק לסדר של ה-Seed Data והבנאי
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, worker_key, role, level, ranking FROM employees")
    rows = cursor.fetchall()
    conn.close()
    
    # מיפוי השורות: row[0]=name, row[1]=worker_key, row[2]=role, row[3]=level, row[4]=ranking
    employees = [Employee(row[0], row[1], row[2], row[3], row[4]) for row in rows]
    
    # 2. חילוץ הפרמטרים שהגיעו אלינו בבקשת הרשת מה-React Frontend
    data = request.json or {}
    days_horizon = data.get('days', 7)
    min_shifts = data.get('min_shifts', 0)
    max_shifts = data.get('max_shifts', 7)
    strategy = data.get('strategy', 'Weekly Balance')
    
    # 3. הרצת מנוע האופטימיזציה
    result = solve_schedule(employees, range(1, days_horizon + 1), min_shifts, max_shifts, strategy)
    
    # 4. החזרת התשובה ל-React
    if result:
        return jsonify({"status": "success", "schedule": result})
    else:
        return jsonify({"status": "error", "message": "האילוצים קשים מדי! לא ניתן למצוא סידור חוקי. נסי להקל על מכסות המינימום/מקסימום."}), 400


if __name__ == '__main__':
    init_db()  # מפעיל ומקים את בסיס הנתונים עם עליית השרת
    app.run(debug=True, port=5000)