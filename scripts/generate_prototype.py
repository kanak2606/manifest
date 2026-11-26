import os
import shutil
import subprocess

html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NoteTrace - Habit Tracker & Deep Focus Analytics Preview</title>
  <style>
    :root {
      --bg-dark: #090d16;
      --bg-card: #111827;
      --bg-card-sub: #172033;
      --border: #1f293d;
      --border-focus: #3b82f6;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --text-sub: #64748b;
      --green: #10b981;
      --green-glow: rgba(16, 185, 129, 0.2);
      --blue: #3b82f6;
      --purple: #8b5cf6;
      --amber: #f59e0b;
      --rose: #f43f5e;
      --cyan: #06b6d4;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif; }
    body { background-color: var(--bg-dark); color: var(--text-main); min-height: 100vh; padding-bottom: 60px; }

    /* Top Nav Bar */
    .navbar {
      display: flex; justify-content: space-between; align-items: center;
      padding: 14px 28px; background: rgba(17, 24, 39, 0.95);
      border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 100;
      backdrop-filter: blur(10px);
    }
    .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.15rem; }
    .brand-badge { background: linear-gradient(135deg, #10b981, #06b6d4); color: #000; font-size: 0.7rem; font-weight: 800; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; }
    .tab-switch { display: flex; background: #0b0f19; padding: 4px; border-radius: 8px; border: 1px solid var(--border); gap: 4px; }
    .tab-btn {
      background: transparent; border: none; color: var(--text-muted); padding: 8px 18px; border-radius: 6px;
      font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: all 0.2s ease;
    }
    .tab-btn.active { background: var(--bg-card); color: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.4); border: 1px solid var(--border); }
    .tab-btn:hover:not(.active) { color: #fff; }

    .container { max-width: 1360px; margin: 24px auto; padding: 0 20px; }

    /* Layout View wrapper */
    .view-container { display: none; }
    .view-container.active { display: block; animation: fadeIn 0.25s ease; }
    @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

    /* NOTES VIEW INTEGRATION */
    .notes-workspace { display: grid; grid-template-columns: 280px 1fr; gap: 20px; }
    .notes-sidebar { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 16px; height: fit-content; }
    .sidebar-header { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-sub); font-weight: 700; margin-bottom: 12px; }
    .note-item { padding: 10px 12px; border-radius: 8px; margin-bottom: 6px; cursor: pointer; transition: background 0.15s; }
    .note-item.active { background: var(--bg-card-sub); border-left: 3px solid var(--green); }
    .note-item-title { font-size: 0.9rem; font-weight: 600; color: var(--text-main); margin-bottom: 2px; }
    .note-item-snippet { font-size: 0.75rem; color: var(--text-sub); }

    .note-editor-pane { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; }

    /* HABIT WIDGET IN NOTE */
    .habit-widget-banner {
      background: linear-gradient(180deg, #131c2e 0%, #0d1320 100%);
      border: 1px solid #1e2c45; border-radius: 12px; padding: 18px 20px; margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.25);
    }
    .hw-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 12px; }
    .hw-title { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.05rem; }
    .streak-badge { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); font-size: 0.8rem; font-weight: 700; padding: 4px 10px; border-radius: 20px; display: inline-flex; align-items: center; gap: 4px; }
    .hw-actions { display: flex; gap: 8px; }
    .btn-small { background: var(--bg-card-sub); border: 1px solid var(--border); color: var(--text-main); font-size: 0.75rem; font-weight: 600; padding: 6px 12px; border-radius: 6px; cursor: pointer; display: inline-flex; align-items: center; gap: 5px; }
    .btn-small:hover { background: #1f2d45; border-color: #3b82f6; }

    /* HABIT CARDS GRID */
    .habits-list { display: flex; flex-direction: column; gap: 12px; }
    .habit-row-card {
      background: #0f1624; border: 1px solid #1c2638; border-radius: 10px; padding: 14px 16px;
      transition: all 0.2s ease;
    }
    .habit-row-card:hover { border-color: #2b3952; }
    .habit-main-line { display: flex; justify-content: space-between; align-items: center; }
    .habit-meta { display: flex; align-items: center; gap: 12px; }
    .habit-icon { font-size: 1.3rem; width: 36px; height: 36px; background: rgba(255,255,255,0.04); border-radius: 8px; display: flex; align-items: center; justify-content: center; }
    .habit-name { font-weight: 600; font-size: 0.95rem; }
    .habit-desc { font-size: 0.75rem; color: var(--text-sub); }

    /* Yes/No Toggle Switch */
    .yes-no-group { display: flex; gap: 6px; background: #090d16; padding: 4px; border-radius: 8px; border: 1px solid #1c2638; }
    .btn-toggle {
      border: none; background: transparent; color: var(--text-muted); font-size: 0.8rem; font-weight: 700;
      padding: 6px 16px; border-radius: 6px; cursor: pointer; transition: all 0.2s;
    }
    .btn-toggle.yes.active { background: #059669; color: #fff; box-shadow: 0 0 10px rgba(16, 185, 129, 0.4); }
    .btn-toggle.no.active { background: #475569; color: #fff; }

    /* CONDITIONAL DRAWER (Revealed on Yes) */
    .conditional-drawer {
      margin-top: 12px; padding-top: 12px; border-top: 1px dashed #1e2c45;
      animation: slideDown 0.2s ease forwards;
    }
    @keyframes slideDown { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
    .drawer-label { font-size: 0.72rem; text-transform: uppercase; font-weight: 700; color: var(--cyan); letter-spacing: 0.04em; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }

    /* Clickable Chips */
    .chips-group { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    .chip {
      background: #151f30; border: 1px solid #233149; color: var(--text-muted); font-size: 0.8rem; font-weight: 600;
      padding: 6px 14px; border-radius: 20px; cursor: pointer; transition: all 0.15s ease; user-select: none;
      display: inline-flex; align-items: center; gap: 6px;
    }
    .chip:hover { border-color: var(--blue); color: #fff; background: #1c2a42; }
    .chip.selected-green { background: rgba(16, 185, 129, 0.15); border-color: var(--green); color: #34d399; font-weight: 700; }
    .chip.selected-blue { background: rgba(59, 130, 246, 0.15); border-color: var(--blue); color: #60a5fa; font-weight: 700; }
    .chip.selected-purple { background: rgba(139, 92, 246, 0.15); border-color: var(--purple); color: #a78bfa; font-weight: 700; }
    .chip.add-chip { border: 1px dashed #3b82f6; color: #38bdf8; background: transparent; font-weight: 600; }
    .chip.add-chip:hover { background: rgba(56, 189, 248, 0.1); }

    /* Weight Log Stepper */
    .weight-card-body { display: flex; align-items: center; gap: 16px; margin-top: 10px; }
    .stepper-box { display: flex; align-items: center; background: #0b0f19; border: 1px solid #233149; border-radius: 8px; overflow: hidden; }
    .stepper-btn { background: #172033; border: none; color: #fff; width: 36px; height: 36px; font-size: 1.1rem; cursor: pointer; font-weight: bold; }
    .stepper-btn:hover { background: #233149; }
    .stepper-val { padding: 0 16px; font-weight: 700; font-size: 1.1rem; color: #f8fafc; }
    .weight-unit { font-size: 0.8rem; color: var(--text-sub); margin-left: 2px; }
    .weight-history-pill { font-size: 0.75rem; color: var(--text-sub); display: flex; gap: 12px; }

    /* NOTE BODY DUMMY */
    .note-content-area { margin-top: 20px; }
    .note-title-input { font-size: 1.6rem; font-weight: 800; color: #fff; margin-bottom: 12px; }
    .checklist-dummy { display: flex; flex-direction: column; gap: 8px; margin-top: 14px; }
    .check-item { display: flex; align-items: center; gap: 10px; font-size: 0.9rem; color: var(--text-muted); }
    .check-box { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #334155; display: flex; align-items: center; justify-content: center; }
    .check-box.checked { background: var(--green); border-color: var(--green); color: #000; font-size: 0.75rem; font-weight: bold; }

    /* ANALYTICS SECTION DASHBOARD */
    .analytics-grid { display: grid; grid-template-columns: repeat(12, 1fr); gap: 20px; }
    .col-4 { grid-column: span 4; }
    .col-6 { grid-column: span 6; }
    .col-8 { grid-column: span 8; }
    .col-12 { grid-column: span 12; }

    .chart-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
    .chart-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .chart-title { font-size: 1rem; font-weight: 700; color: #f8fafc; display: flex; align-items: center; gap: 8px; }
    .chart-subtitle { font-size: 0.75rem; color: var(--text-sub); }

    /* SVG CHART STYLING */
    .donut-container { display: flex; align-items: center; justify-content: space-around; }
    .legend-list { display: flex; flex-direction: column; gap: 8px; }
    .legend-item { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; }
    .legend-color { width: 12px; height: 12px; border-radius: 3px; }

    /* Horizontal Bar Item */
    .hbar-item { margin-bottom: 14px; }
    .hbar-meta { display: flex; justify-content: space-between; font-size: 0.82rem; margin-bottom: 4px; font-weight: 600; }
    .hbar-track { background: #0b0f19; height: 10px; border-radius: 6px; overflow: hidden; }
    .hbar-fill { height: 100%; border-radius: 6px; }

    /* 52-Week Heatmap Grid */
    .heatmap-grid-scroll { overflow-x: auto; padding-bottom: 8px; }
    .heatmap-svg { display: block; }
    .heatmap-legend { display: flex; align-items: center; justify-content: flex-end; gap: 6px; margin-top: 10px; font-size: 0.72rem; color: var(--text-sub); }
    .heat-box { width: 11px; height: 11px; border-radius: 2px; }

    /* Weight Line Chart SVG */
    .weight-chart-svg { width: 100%; height: 180px; overflow: visible; }
  </style>
</head>
<body>

  <!-- NAVBAR -->
  <nav class="navbar">
    <div class="brand">
      <span>NoteTrace</span>
      <span class="brand-badge">Focus & Habit OS</span>
    </div>
    <div class="tab-switch">
      <button class="tab-btn active" onclick="switchTab('notes')">📝 Notes View (Daily Habits)</button>
      <button class="tab-btn" onclick="switchTab('analytics')">📊 Deep Focus & Habit Analysis</button>
    </div>
  </nav>

  <div class="container">

    <!-- ========================================== -->
    <!-- VIEW 1: NOTES SECTION INTEGRATION          -->
    <!-- ========================================== -->
    <div id="view-notes" class="view-container active">
      <div class="notes-workspace">
        
        <!-- Notes Sidebar -->
        <div class="notes-sidebar">
          <div class="sidebar-header">Pinned Notes</div>
          <div class="note-item active">
            <div class="note-item-title">📅 Today - Nov 25, 2026</div>
            <div class="note-item-snippet">Habits done • 4 focus blocks</div>
          </div>
          <div class="note-item">
            <div class="note-item-title">🏗️ NoteTrace Architecture</div>
            <div class="note-item-snippet">FastAPI + Svelte + Termux...</div>
          </div>
          <div class="note-item">
            <div class="note-item-title">💡 Feature Backlog</div>
            <div class="note-item-snippet">Habit tracker & charts...</div>
          </div>
        </div>

        <!-- Note Editor Area with Integrated Habit Tracker -->
        <div class="note-editor-pane">
          
          <!-- HABIT TRACKER COMPONENT (Embedded in Note Header) -->
          <div class="habit-widget-banner">
            <div class="hw-header">
              <div class="hw-title">
                <span>⚡ Daily Habit Check-in</span>
                <span class="streak-badge">🔥 14-Day Streak</span>
              </div>
              <div class="hw-actions">
                <button class="btn-small">+ Add Habit</button>
                <button class="btn-small">⚙️ Reorder</button>
              </div>
            </div>

            <!-- HABITS INTERACTIVE LIST -->
            <div class="habits-list">

              <!-- 1. GYM HABIT -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">🏋️</div>
                    <div>
                      <div class="habit-name">Gym & Fitness</div>
                      <div class="habit-desc">Hit the gym or workout today?</div>
                    </div>
                  </div>
                  <div class="yes-no-group">
                    <button class="btn-toggle yes active" onclick="toggleYesNo(this, 'gym-drawer')">Yes</button>
                    <button class="btn-toggle no" onclick="toggleYesNo(this, 'gym-drawer')">No</button>
                  </div>
                </div>
                <!-- Conditional Drawer for Gym -->
                <div id="gym-drawer" class="conditional-drawer">
                  <div class="drawer-label">Target Muscle Group / Workout Done (Click to select):</div>
                  <div class="chips-group">
                    <span class="chip selected-green" onclick="toggleChip(this)">✓ 🦵 Leg Day</span>
                    <span class="chip selected-green" onclick="toggleChip(this)">✓ 🏃 Cardio</span>
                    <span class="chip" onclick="toggleChip(this)">💪 Chest</span>
                    <span class="chip" onclick="toggleChip(this)">🏋️ Back</span>
                    <span class="chip" onclick="toggleChip(this)">🦾 Arms</span>
                    <span class="chip" onclick="toggleChip(this)">🧘 Shoulders</span>
                    <span class="chip" onclick="toggleChip(this)">🔥 Abs & Core</span>
                    <span class="chip add-chip">+ Add Muscle Group</span>
                  </div>
                </div>
              </div>

              <!-- 2. MEDITATION HABIT -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">🧘</div>
                    <div>
                      <div class="habit-name">Meditation & Breathwork</div>
                      <div class="habit-desc">Practiced mindfulness today?</div>
                    </div>
                  </div>
                  <div class="yes-no-group">
                    <button class="btn-toggle yes active" onclick="toggleYesNo(this, 'med-drawer')">Yes</button>
                    <button class="btn-toggle no" onclick="toggleYesNo(this, 'med-drawer')">No</button>
                  </div>
                </div>
                <!-- Conditional Drawer for Meditation -->
                <div id="med-drawer" class="conditional-drawer">
                  <div class="drawer-label">Select Session Duration:</div>
                  <div class="chips-group">
                    <span class="chip" onclick="selectSingleChip(this)">5 mins</span>
                    <span class="chip" onclick="selectSingleChip(this)">10 mins</span>
                    <span class="chip selected-purple" onclick="selectSingleChip(this)">✓ 15 mins</span>
                    <span class="chip" onclick="selectSingleChip(this)">30 mins</span>
                    <span class="chip" onclick="selectSingleChip(this)">1 Hour</span>
                    <span class="chip add-chip">+ Custom</span>
                  </div>
                </div>
              </div>

              <!-- 3. STUDY HABIT -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">📚</div>
                    <div>
                      <div class="habit-name">Focused Study</div>
                      <div class="habit-desc">Covered course curriculum or study topics?</div>
                    </div>
                  </div>
                  <div class="yes-no-group">
                    <button class="btn-toggle yes active" onclick="toggleYesNo(this, 'study-drawer')">Yes</button>
                    <button class="btn-toggle no" onclick="toggleYesNo(this, 'study-drawer')">No</button>
                  </div>
                </div>
                <!-- Conditional Drawer for Study -->
                <div id="study-drawer" class="conditional-drawer">
                  <div class="drawer-label">Preset Subjects / Courses Studied:</div>
                  <div class="chips-group">
                    <span class="chip selected-blue" onclick="toggleChip(this)">✓ 💻 Data Structures & Algorithms</span>
                    <span class="chip selected-blue" onclick="toggleChip(this)">✓ ⚡ FastAPI Backend</span>
                    <span class="chip" onclick="toggleChip(this)">🏗️ System Design</span>
                    <span class="chip" onclick="toggleChip(this)">🤖 AI & Embeddings</span>
                    <span class="chip add-chip">+ Add Course</span>
                  </div>
                </div>
              </div>

              <!-- 4. DIET & NUTRITION HABIT -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">🥗</div>
                    <div>
                      <div class="habit-name">Diet & Meals</div>
                      <div class="habit-desc">Tracked daily nutrition and calorie goals?</div>
                    </div>
                  </div>
                  <div class="yes-no-group">
                    <button class="btn-toggle yes active" onclick="toggleYesNo(this, 'diet-drawer')">Yes</button>
                    <button class="btn-toggle no" onclick="toggleYesNo(this, 'diet-drawer')">No</button>
                  </div>
                </div>
                <!-- Conditional Drawer for Diet -->
                <div id="diet-drawer" class="conditional-drawer">
                  <div class="drawer-label">Logged Meals & Tags:</div>
                  <div class="chips-group" style="margin-bottom: 8px;">
                    <span class="chip selected-green">✓ 🍳 Breakfast: Eggs & Oats</span>
                    <span class="chip selected-green">✓ 🍗 Lunch: Rice & Chicken Bowl</span>
                    <span class="chip selected-green">✓ 🥜 Supper: Whey & Almonds</span>
                    <span class="chip selected-green">✓ 🥗 Dinner: Clean Salad</span>
                  </div>
                  <div class="chips-group">
                    <span class="chip selected-blue">✓ High Protein (140g)</span>
                    <span class="chip selected-blue">✓ Calorie Deficit</span>
                    <span class="chip add-chip">+ Quick Meal Tag</span>
                  </div>
                </div>
              </div>

              <!-- 5. MEDICINE / SUPPLEMENTS HABIT -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">💊</div>
                    <div>
                      <div class="habit-name">Medicine & Supplements</div>
                      <div class="habit-desc">Taken required daily vitamins?</div>
                    </div>
                  </div>
                  <div class="yes-no-group">
                    <button class="btn-toggle yes active" onclick="toggleYesNo(this, 'meds-drawer')">Yes</button>
                    <button class="btn-toggle no" onclick="toggleYesNo(this, 'meds-drawer')">No</button>
                  </div>
                </div>
                <!-- Conditional Drawer for Medicine -->
                <div id="meds-drawer" class="conditional-drawer">
                  <div class="drawer-label">Dosage Checklist:</div>
                  <div class="chips-group">
                    <span class="chip selected-green" onclick="toggleChip(this)">✓ ☀️ Morning: Multivitamin + D3</span>
                    <span class="chip selected-green" onclick="toggleChip(this)">✓ 🐟 Lunch: Omega-3</span>
                    <span class="chip" onclick="toggleChip(this)">🌙 Night: Magnesium</span>
                    <span class="chip add-chip">+ Add Medicine</span>
                  </div>
                </div>
              </div>

              <!-- 6. WEIGHT TRACKER -->
              <div class="habit-row-card">
                <div class="habit-main-line">
                  <div class="habit-meta">
                    <div class="habit-icon">⚖️</div>
                    <div>
                      <div class="habit-name">Body Weight Log</div>
                      <div class="habit-desc">Log current weight in kg (Track progress)</div>
                    </div>
                  </div>
                  <div style="font-size: 0.8rem; color: #10b981; font-weight: 700;">📉 -0.8 kg this month</div>
                </div>
                <div class="weight-card-body">
                  <div class="stepper-box">
                    <button class="stepper-btn" onclick="stepWeight(-0.1)">-</button>
                    <div class="stepper-val"><span id="weight-val">74.2</span><span class="weight-unit">kg</span></div>
                    <button class="stepper-btn" onclick="stepWeight(0.1)">+</button>
                  </div>
                  <button class="btn-small" style="background:#059669; border-color:#10b981; color:#fff;">💾 Log Today</button>
                  <div class="weight-history-pill">
                    <span>Yesterday: 74.3 kg</span>
                    <span>•</span>
                    <span>Start: 75.0 kg</span>
                  </div>
                </div>
              </div>

            </div>
          </div>

          <!-- Rest of the Note Content -->
          <div class="note-content-area">
            <h1 class="note-title-input">Daily Brain Dump & Agenda — Nov 25</h1>
            <p style="color: var(--text-sub); font-size: 0.85rem; margin-bottom: 16px;">This daily note links directly with your active focus timer and habit statistics.</p>
            <div class="checklist-dummy">
              <div class="check-item"><div class="check-box checked">✓</div> Completed backend habit migrations</div>
              <div class="check-item"><div class="check-box checked">✓</div> Leg day & 20 min cardio session</div>
              <div class="check-item"><div class="check-box"></div> Run 2 deep focus blocks on system design</div>
            </div>
          </div>

        </div>
      </div>
    </div>

    <!-- ========================================== -->
    <!-- VIEW 2: DEEP ANALYTICS & CHARTS DASHBOARD   -->
    <!-- ========================================== -->
    <div id="view-analytics" class="view-container">
      <div class="analytics-grid">
        
        <!-- CHART 1: FOCUS TIME ALLOCATION (DONUT) -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">⏱️ Focus Time Allocation</div>
              <div class="chart-subtitle">Distribution across projects & tags (Past 30 Days)</div>
            </div>
            <span class="streak-badge">28.5 hrs Total</span>
          </div>

          <div class="donut-container">
            <!-- SVG Donut Chart -->
            <svg width="220" height="220" viewBox="0 0 42 42">
              <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#1f293d" stroke-width="5.5"></circle>
              <!-- Work / NoteTrace (45%) -->
              <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#3b82f6" stroke-width="5.5" stroke-dasharray="45 55" stroke-dashoffset="25"></circle>
              <!-- Study / DSA (30%) -->
              <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#10b981" stroke-width="5.5" stroke-dasharray="30 70" stroke-dashoffset="80"></circle>
              <!-- AI Research (15%) -->
              <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#8b5cf6" stroke-width="5.5" stroke-dasharray="15 85" stroke-dashoffset="50"></circle>
              <!-- Writing & Docs (10%) -->
              <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="#f59e0b" stroke-width="5.5" stroke-dasharray="10 90" stroke-dashoffset="35"></circle>
              <g class="donut-text">
                <text x="50%" y="46%" text-anchor="middle" font-size="4" font-weight="800" fill="#fff">28.5h</text>
                <text x="50%" y="58%" text-anchor="middle" font-size="2" fill="#9ca3af">FOCUS</text>
              </g>
            </svg>

            <!-- Legend -->
            <div class="legend-list">
              <div class="legend-item"><div class="legend-color" style="background:#3b82f6;"></div><span>#Work / NoteTrace (45% • 12.8h)</span></div>
              <div class="legend-item"><div class="legend-color" style="background:#10b981;"></div><span>#Study / DSA (30% • 8.5h)</span></div>
              <div class="legend-item"><div class="legend-color" style="background:#8b5cf6;"></div><span>#AI-Research (15% • 4.2h)</span></div>
              <div class="legend-item"><div class="legend-color" style="background:#f59e0b;"></div><span>#Writing / Docs (10% • 3.0h)</span></div>
            </div>
          </div>
        </div>

        <!-- CHART 2: RANKED HORIZONTAL TIME BARS -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">📊 Ranked Project Hours</div>
              <div class="chart-subtitle">Direct comparison by focus duration</div>
            </div>
          </div>
          <div style="padding-top: 6px;">
            <div class="hbar-item">
              <div class="hbar-meta"><span>🏷️ #Work / Backend Engine</span><span>12h 50m (45%)</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width: 45%; background: #3b82f6;"></div></div>
            </div>
            <div class="hbar-item">
              <div class="hbar-meta"><span>🏷️ #Study / Data Structures</span><span>8h 30m (30%)</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width: 30%; background: #10b981;"></div></div>
            </div>
            <div class="hbar-item">
              <div class="hbar-meta"><span>🏷️ #AI / Model Fine-tuning</span><span>4h 15m (15%)</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width: 15%; background: #8b5cf6;"></div></div>
            </div>
            <div class="hbar-item">
              <div class="hbar-meta"><span>🏷️ #Personal / Journaling</span><span>2h 50m (10%)</span></div>
              <div class="hbar-track"><div class="hbar-fill" style="width: 10%; background: #f59e0b;"></div></div>
            </div>
          </div>
        </div>

        <!-- CHART 3: STACKED DAILY FOCUS BAR CHART -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">📅 Daily Focus Composition (Past 7 Days)</div>
              <div class="chart-subtitle">See which category dominated each day</div>
            </div>
          </div>
          <!-- SVG Stacked Bars -->
          <svg width="100%" height="160" viewBox="0 0 450 160">
            <!-- Day 1: Mon -->
            <rect x="25" y="40" width="35" height="40" fill="#3b82f6" rx="3"></rect>
            <rect x="25" y="82" width="35" height="30" fill="#10b981" rx="3"></rect>
            <rect x="25" y="114" width="35" height="15" fill="#8b5cf6" rx="3"></rect>
            <text x="42" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Mon</text>

            <!-- Day 2: Tue -->
            <rect x="85" y="20" width="35" height="65" fill="#3b82f6" rx="3"></rect>
            <rect x="85" y="87" width="35" height="25" fill="#10b981" rx="3"></rect>
            <rect x="85" y="114" width="35" height="15" fill="#f59e0b" rx="3"></rect>
            <text x="102" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Tue</text>

            <!-- Day 3: Wed -->
            <rect x="145" y="50" width="35" height="35" fill="#3b82f6" rx="3"></rect>
            <rect x="145" y="87" width="35" height="40" fill="#10b981" rx="3"></rect>
            <text x="162" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Wed</text>

            <!-- Day 4: Thu -->
            <rect x="205" y="30" width="35" height="50" fill="#3b82f6" rx="3"></rect>
            <rect x="205" y="82" width="35" height="30" fill="#8b5cf6" rx="3"></rect>
            <rect x="205" y="114" width="35" height="15" fill="#10b981" rx="3"></rect>
            <text x="222" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Thu</text>

            <!-- Day 5: Fri -->
            <rect x="265" y="15" width="35" height="70" fill="#3b82f6" rx="3"></rect>
            <rect x="265" y="87" width="35" height="25" fill="#10b981" rx="3"></rect>
            <rect x="265" y="114" width="35" height="15" fill="#f59e0b" rx="3"></rect>
            <text x="282" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Fri</text>

            <!-- Day 6: Sat -->
            <rect x="325" y="60" width="35" height="20" fill="#3b82f6" rx="3"></rect>
            <rect x="325" y="82" width="35" height="45" fill="#10b981" rx="3"></rect>
            <text x="342" y="145" text-anchor="middle" fill="#9ca3af" font-size="11">Sat</text>

            <!-- Day 7: Sun (Today) -->
            <rect x="385" y="35" width="35" height="45" fill="#3b82f6" rx="3"></rect>
            <rect x="385" y="82" width="35" height="35" fill="#10b981" rx="3"></rect>
            <rect x="385" y="119" width="35" height="10" fill="#8b5cf6" rx="3"></rect>
            <text x="402" y="145" text-anchor="middle" fill="#34d399" font-weight="700" font-size="11">Sun</text>
          </svg>
        </div>

        <!-- CHART 4: WEIGHT TREND LINE CHART -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">⚖️ Body Weight Progress (Past 30 Days)</div>
              <div class="chart-subtitle">Progression from 75.0 kg → 74.2 kg (Goal: 72.0 kg)</div>
            </div>
            <span style="color: #10b981; font-weight: 700; font-size: 0.85rem;">-0.8 kg</span>
          </div>
          <!-- SVG Weight Line Chart with Curve and Points -->
          <svg class="weight-chart-svg" viewBox="0 0 500 170">
            <defs>
              <linearGradient id="weightGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#10b981" stop-opacity="0.3"></stop>
                <stop offset="100%" stop-color="#10b981" stop-opacity="0.0"></stop>
              </linearGradient>
            </defs>
            <!-- Goal Line -->
            <line x1="20" y1="130" x2="480" y2="130" stroke="#f59e0b" stroke-dasharray="4" stroke-width="1.5"></line>
            <text x="485" y="133" fill="#f59e0b" font-size="9" text-anchor="start">Goal: 72kg</text>

            <!-- Shaded Area -->
            <path d="M 30,30 L 100,45 L 180,60 L 260,75 L 340,95 L 420,110 L 470,115 L 470,150 L 30,150 Z" fill="url(#weightGrad)"></path>
            <!-- Smooth Line -->
            <path d="M 30,30 L 100,45 L 180,60 L 260,75 L 340,95 L 420,110 L 470,115" fill="none" stroke="#10b981" stroke-width="3"></path>

            <!-- Data Points -->
            <circle cx="30" cy="30" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="100" cy="45" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="180" cy="60" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="260" cy="75" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="340" cy="95" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="420" cy="110" r="4.5" fill="#10b981" stroke="#0f172a" stroke-width="2"></circle>
            <circle cx="470" cy="115" r="5.5" fill="#34d399" stroke="#fff" stroke-width="2"></circle>

            <!-- Labels -->
            <text x="30" y="20" fill="#9ca3af" font-size="10" text-anchor="middle">75.0kg</text>
            <text x="470" y="105" fill="#34d399" font-weight="700" font-size="11" text-anchor="middle">74.2kg</text>
            <text x="30" y="165" fill="#64748b" font-size="9" text-anchor="middle">Nov 1</text>
            <text x="260" y="165" fill="#64748b" font-size="9" text-anchor="middle">Nov 15</text>
            <text x="470" y="165" fill="#64748b" font-size="9" text-anchor="middle">Today</text>
          </svg>
        </div>

        <!-- CHART 5: 52-WEEK GITHUB-STYLE HABIT HEATMAP -->
        <div class="chart-card col-12">
          <div class="chart-header">
            <div>
              <div class="chart-title">🟩 52-Week Habit Consistency Grid</div>
              <div class="chart-subtitle">Combined daily adherence across Gym, Study, Meditation, Diet & Medicine</div>
            </div>
            <div style="font-size: 0.85rem; color: #34d399; font-weight: 700;">🔥 Current Streak: 14 Days Active</div>
          </div>

          <div class="heatmap-grid-scroll">
            <svg class="heatmap-svg" width="980" height="110" viewBox="0 0 980 110">
              <g id="heatmap-cells"></g>
            </svg>
          </div>
          <div class="heatmap-legend">
            <span>Less</span>
            <div class="heat-box" style="background:#1e293b;"></div>
            <div class="heat-box" style="background:#064e3b;"></div>
            <div class="heat-box" style="background:#047857;"></div>
            <div class="heat-box" style="background:#10b981;"></div>
            <div class="heat-box" style="background:#34d399;"></div>
            <span>100% Habits Done</span>
          </div>
        </div>

        <!-- CHART 6: WORKOUT BALANCE POLAR / RADAR -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">💪 Workout Muscle Group Balance</div>
              <div class="chart-subtitle">Sessions logged this month (20 sessions total)</div>
            </div>
          </div>
          <div style="display:flex; align-items:center; justify-content:space-around;">
            <svg width="200" height="180" viewBox="0 0 200 180">
              <!-- Radar Polygon -->
              <polygon points="100,20 170,60 150,140 50,140 30,60" fill="rgba(59, 130, 246, 0.2)" stroke="#3b82f6" stroke-width="2"></polygon>
              <circle cx="100" cy="20" r="4" fill="#3b82f6"></circle>
              <circle cx="170" cy="60" r="4" fill="#3b82f6"></circle>
              <circle cx="150" cy="140" r="4" fill="#3b82f6"></circle>
              <circle cx="50" cy="140" r="4" fill="#3b82f6"></circle>
              <circle cx="30" cy="60" r="4" fill="#3b82f6"></circle>

              <text x="100" y="12" fill="#9ca3af" font-size="10" text-anchor="middle">Legs (6x)</text>
              <text x="180" y="65" fill="#9ca3af" font-size="10">Chest (4x)</text>
              <text x="155" y="155" fill="#9ca3af" font-size="10">Cardio (5x)</text>
              <text x="45" y="155" fill="#9ca3af" font-size="10" text-anchor="end">Arms (3x)</text>
              <text x="20" y="65" fill="#9ca3af" font-size="10" text-anchor="end">Back (4x)</text>
            </svg>
            <div class="legend-list">
              <div class="legend-item"><span style="color:#60a5fa; font-weight:700;">🦵 Legs:</span> 6 workouts</div>
              <div class="legend-item"><span style="color:#60a5fa; font-weight:700;">🏃 Cardio:</span> 5 sessions</div>
              <div class="legend-item"><span style="color:#60a5fa; font-weight:700;">💪 Chest & Back:</span> 8 workouts</div>
              <div class="legend-item"><span style="color:#60a5fa; font-weight:700;">🦾 Arms:</span> 3 workouts</div>
            </div>
          </div>
        </div>

        <!-- CHART 7: MEDITATION & MINDFULNESS INSIGHTS -->
        <div class="chart-card col-6">
          <div class="chart-header">
            <div>
              <div class="chart-title">🧘 Meditation Deep Metrics</div>
              <div class="chart-subtitle">Session frequency & cumulative mindful minutes</div>
            </div>
            <span class="streak-badge">310 Mins Total</span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 10px;">
            <div style="background:#0b0f19; padding:14px; border-radius:8px; border:1px solid #1f293d; text-align:center;">
              <div style="font-size:1.4rem; font-weight:800; color:#a78bfa;">310</div>
              <div style="font-size:0.75rem; color:#9ca3af; margin-top:2px;">Total Minutes</div>
            </div>
            <div style="background:#0b0f19; padding:14px; border-radius:8px; border:1px solid #1f293d; text-align:center;">
              <div style="font-size:1.4rem; font-weight:800; color:#34d399;">22</div>
              <div style="font-size:0.75rem; color:#9ca3af; margin-top:2px;">Days Meditated</div>
            </div>
            <div style="background:#0b0f19; padding:14px; border-radius:8px; border:1px solid #1f293d; text-align:center;">
              <div style="font-size:1.4rem; font-weight:800; color:#38bdf8;">14.1m</div>
              <div style="font-size:0.75rem; color:#9ca3af; margin-top:2px;">Avg Duration</div>
            </div>
          </div>
          <div style="margin-top:16px; background:#0b0f19; border-radius:8px; padding:12px; border:1px solid #1f293d;">
            <div style="font-size:0.75rem; color:#9ca3af; margin-bottom:6px;">Most common duration: <b>15 mins (65% of sessions)</b></div>
            <div style="height:6px; background:#1e293b; border-radius:3px; overflow:hidden;">
              <div style="width:65%; height:100%; background:#8b5cf6;"></div>
            </div>
          </div>
        </div>

      </div>
    </div>

  </div>

  <script>
    // Tab switching
    function switchTab(tab) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view-container').forEach(v => v.classList.remove('active'));
      
      if (tab === 'notes') {
        document.querySelectorAll('.tab-btn')[0].classList.add('active');
        document.getElementById('view-notes').classList.add('active');
      } else {
        document.querySelectorAll('.tab-btn')[1].classList.add('active');
        document.getElementById('view-analytics').classList.add('active');
      }
    }

    // Toggle Yes/No and drawer
    function toggleYesNo(btn, drawerId) {
      const parent = btn.parentElement;
      parent.querySelectorAll('.btn-toggle').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      
      const drawer = document.getElementById(drawerId);
      if (btn.classList.contains('yes')) {
        drawer.style.display = 'block';
      } else {
        drawer.style.display = 'none';
      }
    }

    // Toggle multi-select chips
    function toggleChip(chip) {
      if (chip.classList.contains('selected-green') || chip.classList.contains('selected-blue') || chip.classList.contains('selected-purple')) {
        chip.className = 'chip';
        chip.innerText = chip.innerText.replace('✓ ', '');
      } else {
        chip.classList.add('selected-green');
        chip.innerText = '✓ ' + chip.innerText;
      }
    }

    // Single-select chips
    function selectSingleChip(chip) {
      const group = chip.parentElement;
      group.querySelectorAll('.chip').forEach(c => {
        c.className = 'chip';
        c.innerText = c.innerText.replace('✓ ', '');
      });
      chip.classList.add('selected-purple');
      chip.innerText = '✓ ' + chip.innerText;
    }

    // Weight Stepper
    function stepWeight(delta) {
      const el = document.getElementById('weight-val');
      let curr = parseFloat(el.innerText);
      curr = Math.round((curr + delta) * 10) / 10;
      el.innerText = curr.toFixed(1);
    }

    // Generate 52-week heatmap cells dynamically
    const hmContainer = document.getElementById('heatmap-cells');
    if (hmContainer) {
      const colors = ['#1e293b', '#064e3b', '#047857', '#10b981', '#34d399'];
      let svgHtml = '';
      for (let c = 0; c < 52; c++) {
        for (let r = 0; r < 7; r++) {
          const x = c * 18 + 10;
          const y = r * 14 + 10;
          let colorIdx = Math.floor(Math.random() * 5);
          if (c > 48) colorIdx = Math.floor(Math.random() * 2) + 3;
          if (c < 5) colorIdx = Math.floor(Math.random() * 3);
          const fill = colors[colorIdx];
          svgHtml += `<rect x="${x}" y="${y}" width="12" height="10" rx="2" fill="${fill}"></rect>`;
        }
      }
      hmContainer.innerHTML = svgHtml;
    }
  </script>
</body>
</html>
"""

prototype_path = os.path.abspath("preview_habit_focus.html")
with open(prototype_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"[✓] Created prototype HTML at {prototype_path}")

chrome_bin = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
art_dir = r"C:\Users\Kanak Poddar\.gemini\antigravity\brain\f2ca7952-c671-441d-a274-5f69ee243f04"
os.makedirs(art_dir, exist_ok=True)

# 1. Notes View Screenshot
shot1 = os.path.join(art_dir, "habits_notes_view.png")
cmd1 = [
    chrome_bin,
    "--headless=new",
    "--disable-gpu",
    "--window-size=1400,1250",
    f"--screenshot={shot1}",
    f"file:///{prototype_path.replace(os.sep, '/')}"
]
print("[*] Capturing Notes View Screenshot...")
subprocess.run(cmd1, check=True)
print(f"[✓] Captured: {shot1} ({os.path.getsize(shot1)} bytes)")

# 2. Analytics View Screenshot
html_analytics = html_content.replace(
    'class="tab-btn active" onclick="switchTab(\'notes\')"',
    'class="tab-btn" onclick="switchTab(\'notes\')"'
).replace(
    'class="tab-btn" onclick="switchTab(\'analytics\')"',
    'class="tab-btn active" onclick="switchTab(\'analytics\')"'
).replace(
    'id="view-notes" class="view-container active"',
    'id="view-notes" class="view-container"'
).replace(
    'id="view-analytics" class="view-container"',
    'id="view-analytics" class="view-container active"'
)

analytics_html_path = os.path.abspath("preview_analytics_only.html")
with open(analytics_html_path, "w", encoding="utf-8") as f:
    f.write(html_analytics)

shot2 = os.path.join(art_dir, "habits_analytics_view.png")
cmd2 = [
    chrome_bin,
    "--headless=new",
    "--disable-gpu",
    "--window-size=1400,1200",
    f"--screenshot={shot2}",
    f"file:///{analytics_html_path.replace(os.sep, '/')}"
]
print("[*] Capturing Analytics View Screenshot...")
subprocess.run(cmd2, check=True)
print(f"[✓] Captured: {shot2} ({os.path.getsize(shot2)} bytes)")

# Copy HTML to artifact folder as well
shutil.copy(prototype_path, os.path.join(art_dir, "preview_habit_focus.html"))
print("[✓] Copied interactive HTML to artifact folder.")
