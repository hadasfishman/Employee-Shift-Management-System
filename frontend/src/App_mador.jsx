import React, { useState } from 'react';
import * as XLSX from 'xlsx';

function App() {
  // 1. הגדרות כלליות
  const [days, setDays] = useState(7);
  const [maxShifts, setMaxShifts] = useState(5);
  const [minShifts, setMinShifts] = useState(2);
  const [consecutiveRest, setConsecutiveRest] = useState(true);
  const [strategy, setStrategy] = useState('fairness');
  const [currentSeed, setCurrentSeed] = useState(1);

  // רשימת מאיישים דינמית לפי דרישת המשתמש האחרונה
  const [employees, setEmployees] = useState([
    { name: "Michal", rank: 2 },
    { name: "Elhanan", rank: 1 },
    { name: "Ofri", rank: 3 },   
    { name: "Dori", rank: 3 },   
    { name: "Yoav", rank: 1 },
    { name: "Neta", rank: 3 },  
    { name: "Adi", rank: 2 },
    { name: "Romi", rank: 2 },
    { name: "Gili", rank: 1 },
    { name: "Noga", rank: 1 }
  ]);

  const [newEmpName, setNewEmpName] = useState('');
  const [newEmpRank, setNewEmpRank] = useState(1);

  const hourOptions = Array.from({ length: 24 }, (_, i) => String(i).padStart(2, '0') + ':00');

  // 2. הגדרות משמרת
  const [shifts, setShifts] = useState([
    { id: 'morning', name: 'משמרת יום ☀️', startHour: '08:00', endHour: '20:00', count: 2, requireTeamLead: true, requireSenior: false, isCustom: false, active: true },
    { id: 'night', name: 'משמרת לילה 🌙', startHour: '20:00', endHour: '08:00', count: 1, requireTeamLead: false, requireSenior: true, isCustom: false, active: true }
  ]);

  const [newShiftName, setNewShiftName] = useState('');
  const [newStartHour, setNewStartHour] = useState('08:00');
  const [newEndHour, setNewEndHour] = useState('20:00');

  // 3. היסטוריית שיבוץ
  const [useHistoryFromDB, setUseHistoryFromDB] = useState(true);
  const [lastNightWorker, setLastNightWorker] = useState('');

  const [schedule, setSchedule] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [saveSuccessMessage, setSaveSuccessMessage] = useState('');

  // הורדת טמפלייט אקסל
  const downloadTemplate = () => {
    const templateRows = [
      { 'שם': 'ישראל ישראלי', 'דרגה': 3 },
      { 'שם': 'מיכל כהן', 'דרגה': 2 },
      { 'שם': 'אבי לוי', 'דרגה': 1 }
    ];
    const worksheet = XLSX.utils.json_to_sheet(templateRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'רשימת מאיישים למילוי');
    XLSX.writeFile(workbook, 'טמפלייט_מאיישים_למילוי.xlsx');
  };

  // קריאת קובץ אקסל
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (evt) => {
      try {
        const data = evt.target.result;
        const workbook = XLSX.read(data, { type: 'binary' });
        const worksheet = workbook.Sheets[workbook.SheetNames[0]];
        const jsonData = XLSX.utils.sheet_to_json(worksheet);

        const parsedEmployees = jsonData.map(row => {
          const name = row['שם'] || row['Name'] || row['name'];
          const rankVal = row['דרגה'] || row['Rank'] || row['rank'];
          return { name: String(name).trim(), rank: parseInt(rankVal) || 1 };
        }).filter(emp => emp.name && emp.name !== 'undefined' && emp.name !== 'ישראל ישראלי' && emp.name !== 'מיכל כהן' && emp.name !== 'אבי לוי');

        if (parsedEmployees.length === 0) throw new Error("לא נמצאו נתוני מאיישים תקינים בקובץ");
        setEmployees(parsedEmployees);
        alert(`נטענו בהצלחה ${parsedEmployees.length} מאיישים מהקובץ!`);
      } catch (err) {
        alert("שגיאה בקריאת קובץ האקסל: " + err.message);
      }
    };
    reader.readAsBinaryString(file);
  };

  // הוספה ידנית
  const handleAddEmployeeManual = (e) => {
    e.preventDefault();
    if (!newEmpName.trim()) return;
    if (employees.some(emp => emp.name.toLowerCase() === newEmpName.trim().toLowerCase())) {
      alert("מאיייש עם שם זה כבר קיים במערכת");
      return;
    }
    setEmployees([...employees, { name: newEmpName.trim(), rank: parseInt(newEmpRank) }]);
    setNewEmpName('');
    setNewEmpRank(1);
  };

  const handleDeleteEmployee = (nameToRemove) => {
    setEmployees(employees.filter(emp => emp.name !== nameToRemove));
  };

  const addCustomShift = (e) => {
    e.preventDefault();
    if (!newShiftName.trim()) return;
    setShifts([...shifts, {
      id: 'custom_' + Date.now(), name: newShiftName, startHour: newStartHour, endHour: newEndHour, count: 1, requireTeamLead: false, requireSenior: false, isCustom: true, active: true
    }]);
    setNewShiftName('');
    setNewStartHour('08:00');
    setNewEndHour('20:00');
  };

  const updateShift = (id, field, value) => {
    setShifts(shifts.map(s => s.id === id ? { ...s, [field]: value } : s));
  };

  const deleteShift = (id) => {
    setShifts(shifts.filter(s => s.id !== id));
  };

  // פונקציית השיבוץ המרכזית
  const generateSchedule = async (forcedSeed = null) => {
    setLoading(true);
    setError(null);
    setSaveSuccessMessage('');
    const seedToSend = forcedSeed !== null ? forcedSeed : currentSeed;

    try {
      const response = await fetch('http://127.0.0.1:5000/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          days_horizon: parseInt(days),
          max_shifts_per_employee: parseInt(maxShifts),
          min_shifts_per_week: parseInt(minShifts),
          prefer_consecutive_rest: consecutiveRest,
          optimization_strategy: strategy,
          seed: seedToSend,
          employees_list: employees,
          active_shifts: shifts.filter(s => s.active).map(s => ({
            id: s.id, name: s.name, start_hour: s.startHour, end_hour: s.endHour, count: s.count, require_team_lead: s.requireTeamLead, require_senior: s.requireSenior
          })),
          history: { use_db: useHistoryFromDB, manual_last_night_worker: useHistoryFromDB ? null : lastNightWorker }
        }),
      });

      if (!response.ok) throw new Error('השרת החזיר שגיאה בחישוב האופטימיזציה');
      
      const data = await response.json();
      if (data.status === 'success') setSchedule(data.schedule);
      else throw new Error(data.message || 'נכשל בחישוב הסידור');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshSchedule = () => {
    const nextSeed = Math.floor(Math.random() * 10000) + 1;
    setCurrentSeed(nextSeed);
    generateSchedule(nextSeed);
  };

  // 🔒 פונקציה חדשה: נעילה ואישור הסידור הנוכחי לתוך מסד הנתונים של פלאסק
  const saveScheduleToDB = async () => {
    if (!schedule) return;
    try {
      const response = await fetch('http://127.0.0.1:5000/api/save_schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ schedule }),
      });
      const data = await response.json();
      if (data.status === 'success') {
        setSaveSuccessMessage('✅ הסידור ננעל ואושר רשמית ב-DB! הוא ישמש כהיסטוריה עבור הריצה הבאה.');
      } else {
        alert('שגיאה בשמירה: ' + data.message);
      }
    } catch (err) {
      alert('נכשלה התקשורת עם השרת בשמירה: ' + err.message);
    }
  };

  const exportToExcel = () => {
    if (!schedule) return;
    const excelRows = schedule.map(item => {
      const sortedStaff = item.Staff && Array.isArray(item.Staff) ? [...item.Staff].sort((a, b) => b.rank - a.rank) : [];
      const staffNames = sortedStaff.map(p => p.name + (p.rank === 3 ? ' (ר"ת)' : p.rank === 2 ? ' (ותיק/ה)' : '')).join(', ');
      return { 'יום': item.Day, 'משמרת': item.ShiftName, 'שעות': item.Hours, 'מאיישים': staffNames };
    });
    const worksheet = XLSX.utils.json_to_sheet(excelRows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, 'לוח משמרות');
    XLSX.writeFile(workbook, `לוח_משמרות_${new Date().toISOString().slice(0,10)}.xlsx`);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-gray-100 font-sans p-8" dir="rtl">
      <div className="max-w-6xl mx-auto">
        
        <header className="mb-10 text-center border-b border-gray-800 pb-6">
          <h1 className="text-4xl font-extrabold tracking-tight mb-2 bg-gradient-to-r from-blue-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
            מערכת שיבוץ משמרות חכמה
          </h1>
          <p className="text-sm font-light uppercase tracking-widest text-gray-400">
            מנוע אופטימיזציה מתמטי <span className="text-gray-500">|</span> CP-SAT Solver
          </p>
        </header>

        {/* פאנל ניהול מאיישים */}
        <div className="bg-gray-850 p-5 rounded-xl mb-6 border border-gray-700 shadow-md">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-gray-700/60 pb-3 mb-4">
            <div>
              <h4 className="text-base font-bold text-gray-200">👥 ניהול רשימת מאיישים במערכת</h4>
              <p className="text-xs text-gray-400 mt-0.5">מאגר נוכחי: <span className="text-blue-400 font-semibold">{employees.length} אנשים</span> ({employees.filter(e=>e.rank===3).length} ראשי תא, {employees.filter(e=>e.rank===2).length} ותיקים, {employees.filter(e=>e.rank===1).length} צעירים).</p>
            </div>
            <div className="flex gap-2.5">
              <button onClick={downloadTemplate} className="bg-gray-800 hover:bg-gray-750 text-gray-300 text-xs font-semibold py-1.5 px-3 rounded-lg border border-gray-600 flex items-center gap-1"><span>הורד פורמט למילוי</span>📥</button>
              <label className="bg-gray-700 hover:bg-gray-650 text-gray-200 text-xs font-semibold py-1.5 px-3 rounded-lg cursor-pointer border border-gray-600 flex items-center gap-1"><span>טען מאקסל</span>📊<input type="file" accept=".xlsx, .xls" onChange={handleFileUpload} className="hidden" /></label>
            </div>
          </div>

          <div className="flex flex-wrap gap-2 mb-4 max-h-36 overflow-y-auto p-1 bg-gray-900/40 rounded-lg border border-gray-800">
            {employees.map((emp, idx) => (
              <span key={idx} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${emp.rank === 3 ? 'bg-amber-500/15 text-amber-300 border-amber-500/40 font-semibold' : emp.rank === 2 ? 'bg-blue-500/15 text-blue-300 border-blue-500/40 font-medium' : 'bg-gray-750 text-gray-200 border-gray-600/80'}`}>
                <span>{emp.name} {emp.rank === 3 ? '(ר"ת)' : emp.rank === 2 ? '(ותיק/ה)' : '(צעיר/ה)'}</span>
                <button onClick={() => handleDeleteEmployee(emp.name)} className="text-gray-500 hover:text-red-400 font-bold text-[10px] mr-1 bg-gray-900/30 w-3.5 h-3.5 rounded-full flex items-center justify-center">✕</button>
              </span>
            ))}
          </div>

          <form onSubmit={handleAddEmployeeManual} className="flex flex-col sm:flex-row items-end sm:items-center gap-3 bg-gray-800/60 p-2.5 rounded-lg border border-gray-750">
            <span className="text-xs font-medium text-gray-400 whitespace-nowrap">➕ הוספה מהירה:</span>
            <input type="text" placeholder="שם החוקר/ת..." value={newEmpName} onChange={(e) => setNewEmpName(e.target.value)} className="bg-gray-700 border border-gray-600 rounded px-2.5 py-1 text-xs text-white focus:outline-none w-full sm:w-44" />
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-gray-400">דרגה/דירוג:</span>
              <select value={newEmpRank} onChange={(e) => setNewEmpRank(e.target.value)} className="bg-gray-700 text-white text-xs rounded p-1 border border-gray-600 cursor-pointer focus:outline-none">
                <option value={1}>חוקר צעיר (דרגה 1)</option>
                <option value={2}>חוקר ותיק (דרגה 2)</option>
                <option value={3}>ראש תא (דרגה 3)</option>
              </select>
            </div>
            <button type="submit" className="bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold py-1.5 px-3.5 rounded transition-colors mr-auto sm:mr-0">הוסף לרשימה</button>
          </form>
        </div>

        <div className="bg-gray-800 p-6 rounded-xl shadow-lg mb-8 border border-gray-700">
          
          {/* 1. הגדרות כלליות */}
          <section className="mb-8">
            <h3 className="text-lg font-bold text-blue-400 mb-4 border-b border-gray-700 pb-1">1. הגדרות כלליות</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
              <div><label className="block text-xs font-medium text-gray-400 mb-1">אופק שיבוץ (בימים):</label><input type="number" value={days} onChange={(e) => setDays(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white focus:outline-none" /></div>
              <div><label className="block text-xs font-medium text-gray-400 mb-1">מקסימום משמרות בשבוע:</label><input type="number" value={maxShifts} onChange={(e) => setMaxShifts(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white focus:outline-none" /></div>
              <div><label className="block text-xs font-medium text-gray-400 mb-1">מינימום משמרות בשבוע:</label><input type="number" value={minShifts} onChange={(e) => setMinShifts(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white focus:outline-none" /></div>
              <div>
                <label className="block text-xs font-medium text-gray-400 mb-1">אסטרטגיית שיבוץ:</label>
                <select value={strategy} onChange={(e) => setStrategy(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-1.5 text-white focus:outline-none">
                  <option value="fairness">חלוקה הוגנת וצמצום פערים</option>
                  <option value="continuity">שמירה על רצף באיוש</option>
                  <option value="balance">צמצום מקסימלי של כמות המאיישים</option>
                </select>
              </div>
            </div>
            <div className="mt-3">
              <label className="flex items-center space-x-2 space-x-reverse cursor-pointer">
                <input type="checkbox" checked={consecutiveRest} onChange={(e) => setConsecutiveRest(e.target.checked)} className="rounded bg-gray-700 border-gray-600 text-blue-500 w-4 h-4" />
                <span className="text-sm text-gray-300 mr-2 font-medium">העדפת ימי מנוחה רצופים</span>
              </label>
            </div>
          </section>

          {/* 2. הגדרות משמרת */}
          <section className="mb-8">
            <h3 className="text-lg font-bold text-blue-400 mb-4 border-b border-gray-700 pb-1">2. הגדרות משמרת</h3>
            <div className="space-y-3 mb-4">
              {shifts.map((shift) => (
                <div key={shift.id} className={`grid grid-cols-1 md:grid-cols-12 gap-3 items-center p-3 rounded-lg border ${shift.active ? 'bg-gray-750 border-gray-600' : 'bg-gray-800/40 border-gray-800 opacity-50'}`}>
                  <label className="flex items-center space-x-2 space-x-reverse font-semibold cursor-pointer md:col-span-3">
                    <input type="checkbox" checked={shift.active} onChange={(e) => updateShift(shift.id, 'active', e.target.checked)} className="rounded bg-gray-700 border-gray-600 text-blue-500 w-4 h-4" />
                    <span className="text-gray-200 mr-2 text-sm">{shift.name}</span>
                  </label>
                  <div className="flex items-center space-x-1 space-x-reverse md:col-span-3 bg-gray-700/50 p-1.5 rounded-lg border border-gray-600/50">
                    <span className="text-xs text-gray-400 ml-1">שעות:</span>
                    <select disabled={!shift.active} value={shift.startHour} onChange={(e) => updateShift(shift.id, 'startHour', e.target.value)} className="bg-gray-700 text-white text-xs rounded p-1 border border-gray-600">{hourOptions.map(h => <option key={h} value={h}>{h}</option>)}</select>
                    <span className="text-xs text-gray-500 font-bold mx-0.5">עד</span>
                    <select disabled={!shift.active} value={shift.endHour} onChange={(e) => updateShift(shift.id, 'endHour', e.target.value)} className="bg-gray-700 text-white text-xs rounded p-1 border border-gray-600">{hourOptions.map(h => <option key={h} value={h}>{h}</option>)}</select>
                  </div>
                  <div className="flex items-center space-x-2 space-x-reverse md:col-span-2">
                    <span className="text-xs text-gray-400 whitespace-nowrap">חוקרים:</span>
                    <input type="number" disabled={!shift.active} value={shift.count} onChange={(e) => updateShift(shift.id, 'count', parseInt(e.target.value) || 0)} className="w-12 bg-gray-700 border border-gray-600 rounded p-1 text-center text-white text-sm" />
                  </div>
                  <div className="flex items-center gap-3 md:col-span-3">
                    <label className="flex items-center space-x-1.5 space-x-reverse cursor-pointer"><input type="checkbox" disabled={!shift.active} checked={shift.requireTeamLead} onChange={(e) => updateShift(shift.id, 'requireTeamLead', e.target.checked)} className="rounded bg-gray-700 border-gray-600 text-amber-500 w-3.5 h-3.5 focus:ring-0" /><span className="text-xs text-gray-400 mr-1">ראש תא</span></label>
                    <label className="flex items-center space-x-1.5 space-x-reverse cursor-pointer"><input type="checkbox" disabled={!shift.active} checked={shift.requireSenior} onChange={(e) => updateShift(shift.id, 'requireSenior', e.target.checked)} className="rounded bg-gray-700 border-gray-600 text-blue-500 w-3.5 h-3.5 focus:ring-0" /><span className="text-xs text-gray-400 mr-1">חוקר ותיק</span></label>
                  </div>
                  <div className="text-left md:col-span-1">{shift.isCustom && <button onClick={() => deleteShift(shift.id)} className="text-xs text-red-400 hover:text-red-300">מחק</button>}</div>
                </div>
              ))}
            </div>
            <form onSubmit={addCustomShift} className="bg-gray-850 p-4 rounded-lg border border-gray-750 border-dashed grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div><label className="block text-xs text-gray-400 mb-1">שם משמרת נוספת:</label><input type="text" placeholder="משמרת אופליין..." value={newShiftName} onChange={(e) => setNewShiftName(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none" /></div>
              <div><label className="block text-xs text-gray-400 mb-1">שעת התחלה:</label><select value={newStartHour} onChange={(e) => setNewStartHour(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white">{hourOptions.map(h => <option key={h} value={h}>{h}</option>)}</select></div>
              <div><label className="block text-xs text-gray-400 mb-1">שעת סיום:</label><select value={newEndHour} onChange={(e) => setNewEndHour(e.target.value)} className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-1.5 text-sm text-white">{hourOptions.map(h => <option key={h} value={h}>{h}</option>)}</select></div>
              <button type="submit" className="bg-gray-700 border border-gray-600 text-blue-400 font-bold py-1.5 px-4 rounded-lg text-sm">+ הוסף למערך</button>
            </form>
          </section>

          {/* 3. היסטוריית שיבוץ */}
          <section className="mb-6">
            <h3 className="text-lg font-bold text-blue-400 mb-4 border-b border-gray-700 pb-1">3. היסטוריית שיבוץ</h3>
            <div className="bg-gray-750 p-4 rounded-lg border border-gray-600 grid grid-cols-1 md:grid-cols-2 gap-6">
              <div><label className="flex items-center space-x-2 space-x-reverse cursor-pointer"><input type="radio" checked={useHistoryFromDB} onChange={() => setUseHistoryFromDB(true)} className="text-blue-500 bg-gray-700" /><span className="text-sm font-medium mr-2 text-gray-200">טען היסטוריה אוטומטית ממסד הנתונים (מומלץ)</span></label></div>
              <div>
                <label className="flex items-center space-x-2 space-x-reverse cursor-pointer"><input type="radio" checked={!useHistoryFromDB} onChange={() => setUseHistoryFromDB(false)} className="text-blue-500 bg-gray-700" /><span className="text-sm font-medium mr-2 text-gray-200">הזן נתוני פתיחה באופן ידני</span></label>
                {!useHistoryFromDB && <div className="mt-2 pr-6"><input type="text" placeholder="למשל: Michal" value={lastNightWorker} onChange={(e) => setLastNightWorker(e.target.value)} className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-1 text-sm text-white w-full focus:outline-none" /></div>}
              </div>
            </div>
          </section>

          <div className="flex gap-4">
            <button onClick={() => generateSchedule(null)} disabled={loading} className={`flex-1 py-3 px-6 rounded-lg font-bold text-white shadow-md text-lg ${loading ? 'bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}>{loading ? 'מחשב פתרון...' : 'שבץ'}</button>
            {schedule && <button onClick={handleRefreshSchedule} disabled={loading} className="py-3 px-5 bg-gray-700 hover:bg-gray-600 text-blue-400 font-bold rounded-lg text-lg border border-gray-600 flex items-center gap-2"><span>שבץ מחדש</span><span className={`${loading ? 'animate-spin' : ''}`}>🔄</span></button>}
          </div>
        </div>

        {error && <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-lg mb-8">⚠️ שגיאה: {error}</div>}

        {/* הודעת הצלחה על שמירה ב-DB */}
        {saveSuccessMessage && (
          <div className="bg-emerald-900/40 border border-emerald-500 text-emerald-200 p-3 rounded-lg mb-6 text-sm font-medium">
            {saveSuccessMessage}
          </div>
        )}

        {schedule && Array.isArray(schedule) && (
          <div className="space-y-4">
            {/* סרגל כפתורי פלט מעודכן עם נעילת DB */}
            <div className="flex justify-end bg-gray-850 p-2 rounded-lg border border-gray-700/60 max-w-fit mr-auto gap-3">
              <button 
                onClick={saveScheduleToDB} 
                className="px-4 py-1.5 bg-blue-700 hover:bg-blue-600 text-white text-sm font-bold rounded-md shadow flex items-center gap-1.5 transition-colors border border-blue-600"
              >
                <span>אשר שיבוץ ושמור בהיסטוריה</span><span>🔒</span>
              </button>
              <button onClick={exportToExcel} className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-bold rounded-md shadow flex items-center gap-1.5 transition-colors">
                <span>ייצא לאקסל</span><span>📊</span>
              </button>
            </div>

            <div className="bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700 overflow-x-auto">
              <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-4 mb-6 border-b border-gray-700 pb-4">
                <div><h2 className="text-xl font-bold text-gray-200">לוח משמרות</h2><p className="text-xs text-gray-400 mt-1">סטטוס: פתרון אופטימלי (CP-SAT)</p></div>
                <div className="flex items-center gap-4 bg-gray-850 p-2 rounded-lg border border-gray-700 text-xs">
                  <span className="text-gray-400 font-medium">מקרא סימונים:</span>
                  <div className="flex items-center gap-1.5"><span className="w-3 h-3 bg-amber-500/20 border border-amber-500/50 rounded"></span><span className="text-amber-300 font-semibold">ראש תא</span></div>
                  <div className="flex items-center gap-1.5 border-r border-gray-700 pr-4"><span className="w-3 h-3 bg-blue-500/20 border border-blue-500/50 rounded"></span><span className="text-blue-300 font-medium">חוקר ותיק</span></div>
                  <div className="flex items-center gap-1.5 border-r border-gray-700 pr-4"><span className="w-3 h-3 bg-gray-700/60 border border-gray-600/70 rounded"></span><span className="text-gray-300">חוקר צעיר</span></div>
                </div>
              </div>

              <table className="w-full text-right border-collapse">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-400 bg-gray-850/50 text-sm">
                    <th className="p-3 w-1/6">יום</th>
                    <th className="p-3 w-1/4">משמרת</th>
                    <th className="p-3 w-7/12">מאיישים</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule.map((item, index) => {
                    const isNight = item.ShiftName?.includes('לילה');
                    const isDay = item.ShiftName?.includes('יום');
                    const isOffline = item.ShiftName?.includes('אופליין');

                    const shiftBadgeColor = isNight ? 'bg-purple-950/40 text-purple-300 border-purple-800/60' : isDay ? 'bg-blue-950/40 text-blue-300 border-blue-800/60' : isOffline ? 'bg-pink-950/40 text-pink-300 border-pink-800/60' : 'bg-gray-750 text-gray-300 border-gray-600';
                    const sortedStaff = item.Staff && Array.isArray(item.Staff) ? [...item.Staff].sort((a, b) => b.rank - a.rank) : [];

                    return (
                      <tr key={index} className="border-b border-gray-700/60 hover:bg-gray-750 transition-colors">
                        <td className="p-3 font-bold text-gray-300 bg-gray-800/30">{item.Day}</td>
                        <td className="p-3"><span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border ${shiftBadgeColor}`}>{item.ShiftName || 'משמרת כללית'}</span></td>
                        <td className="p-3">
                          <div className="flex flex-wrap gap-2">
                            {sortedStaff.length > 0 ? sortedStaff.map((person, pIdx) => (
                              <span key={pIdx} className={`inline-flex items-center px-3 py-1 rounded-lg text-sm font-medium border ${person.rank === 3 ? 'bg-amber-500/20 text-amber-300 border-amber-500/50 font-semibold' : person.rank === 2 ? 'bg-blue-500/20 text-blue-300 border-blue-500/50 font-medium' : 'bg-gray-700/60 text-gray-200 border-gray-600/70'}`}>
                                {person.name}
                              </span>
                            )) : <span className="text-gray-500 text-xs italic">לא נקבע שיבוץ מאיישים</span>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;