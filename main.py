
from ortools.sat.python import cp_model

# --- 1. הגדרת הנתונים (הקלט לפרויקט) ---

# נתונים בסיסיים לדוגמה:
NUM_EMPLOYEES = 3
NUM_SHIFTS = 3 # בוקר, ערב, לילה
NUM_DAYS = 7   # ימי השבוע

# שמות וישויות:
all_employees = range(NUM_EMPLOYEES)
all_shifts = range(NUM_SHIFTS)
all_days = range(NUM_DAYS)

# דרישות: כמה עובדים נדרשים לכל משמרת/יום
# לצורך הדוגמה, נניח שצריך עובד 1 בכל משמרת:
SHIFT_DEMAND = 1 


# --- 2. יצירת המודל והמשתנים ---

model = cp_model.CpModel()

# משתנה החלטה בינארי:
# shifts[(e, d, s)] = 1 אם עובד e משובץ ליום d ולמשמרת s, ו-0 אחרת.
shifts = {}
for e in all_employees:
    for d in all_days:
        for s in all_shifts:
            shifts[(e, d, s)] = model.NewBoolVar(f'shift_e{e}_d{d}_s{s}')


# --- 3. הגדרת אילוצי החובה (Hard Constraints) ---

# אילוץ 1: כל משמרת צריכה להיות מאוישת (כיסוי הדרישה)
for d in all_days:
    for s in all_shifts:
        # סכום השיבוצים ליום d ומשמרת s חייב להיות שווה לדרישה (1)
        model.Add(sum(shifts[(e, d, s)] for e in all_employees) == SHIFT_DEMAND)

# אילוץ 2: כל עובד יכול לעבוד משמרת אחת לכל היותר ביום
# (עובד לא יכול לעבוד משמרת בוקר ומשמרת ערב באותו היום)
for e in all_employees:
    for d in all_days:
        # סכום השיבוצים של עובד e ביום d בכל המשמרות צריך להיות לכל היותר 1
        model.Add(sum(shifts[(e, d, s)] for s in all_shifts) <= 1)


# --- 4. אופטימיזציה (פונקציית מטרה) ---

# מטרה: למקסם את סך המשמרות המשובצות.
# זהו שלב מינימלי המבטיח שהמודל ינסה למצוא פתרון מלא.
model.Maximize(sum(shifts.values()))


# --- 5. הרצת הפותר (Solver) ---

solver = cp_model.CpSolver()
solver.parameters.log_search_progress = True # כדי לראות את תהליך החיפוש
status = solver.Solve(model)


# --- 6. הצגת התוצאות ---

if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
    print("found optimal shift board\n")
    
    # הדפסת כותרות ימים
    header = "shift | " + " | ".join(f"day {d+1}" for d in all_days)
    print("-" * len(header))
    print(header)
    print("-" * len(header))

    # הדפסת התוצאות לכל משמרת (עובדים ששובצו)
    for s in all_shifts:
        row = f"shift' {s+1}  | "
        for d in all_days:
            assigned_employee = "---"
            for e in all_employees:
                if solver.Value(shifts[(e, d, s)]) == 1:
                    assigned_employee = f"worker{e+1}" # מציג את מספר העובד ששובץ
                    break
            row += f"{assigned_employee} | "
        print(row.strip())
    print("-" * len(header))

else:
    print("can't find good solution")