//@version=5
indicator("KeedSweepBot - FINAL V2 + 1min Confirm", overlay=true, max_lines_count=500)

// === INPUTS ===
tol5 = input.float(15, "5min Tolerance %", minval=1, maxval=50) / 100
tol1 = input.float(5, "1min Tolerance % - Equal Highs/Lows", minval=1, maxval=20) / 100
showLines = input.bool(true, "Show Prev 1H Lines")

// === PREVIOUS 1H HIGH / LOW (RED LINES) ===
prevHigh1H = request.security(syminfo.tickerid, "60", high[1], lookahead=barmerge.lookahead_off)
prevLow1H  = request.security(syminfo.tickerid, "60", low[1], lookahead=barmerge.lookahead_off)
prevRange = prevHigh1H - prevLow1H
midLine = (prevHigh1H + prevLow1H) / 2

plot(showLines ? prevHigh1H : na, "Prev 1H High", color=color.new(color.red, 0), style=plot.style_linebr, linewidth=2)
plot(showLines ? prevLow1H : na, "Prev 1H Low", color=color.new(color.red, 0), style=plot.style_linebr, linewidth=2)
plot(showLines ? midLine : na, "TP1 50%", color=color.new(color.gray, 0), style=plot.style_linebr, linewidth=1)

// === TIME ===
hourMin = minute(time)
isFirst15 = hourMin <= 15

// === STRATEGY 1 - SWEEP (First 0:15 only) ===
sweepTop = isFirst15 and high > prevHigh1H and close < prevHigh1H
sweepBottom = isFirst15 and low < prevLow1H and close > prevLow1H

plotshape(sweepTop, title="S1 SELL", location=location.abovebar, color=color.red, style=shape.triangledown, size=size.small, text="S1 SELL")
plotshape(sweepBottom, title="S1 BUY", location=location.belowbar, color=color.green, style=shape.triangleup, size=size.small, text="S1 BUY")

// === STRATEGY 2 - DOUBLE TOP / BOTTOM ON 5min ===
leftBars = 3
rightBars = 3
ph = ta.pivothigh(high, leftBars, rightBars)
pl = ta.pivotlow(low, leftBars, rightBars)

var float lastPH1 = na
var float lastPH2 = na
var float lastPL1 = na
var float lastPL2 = na
var float neckDT = na
var float neckDB = na

if not na(ph)
    lastPH2 := lastPH1
    lastPH1 := ph
    neckDT := ta.lowest(low, 20)

if not na(pl)
    lastPL2 := lastPL1
    lastPL1 := pl
    neckDB := ta.highest(high, 20)

isDT_5m = not na(lastPH1) and not na(lastPH2) and math.abs(lastPH1 - lastPH2) <= prevRange * tol5 and math.abs(lastPH1 - prevHigh1H) <= prevRange * 0.5 and math.abs(lastPH2 - prevHigh1H) <= prevRange * 0.5
isDB_5m = not na(lastPL1) and not na(lastPL2) and math.abs(lastPL1 - lastPL2) <= prevRange * tol5 and math.abs(lastPL1 - prevLow1H) <= prevRange * 0.5 and math.abs(lastPL2 - prevLow1H) <= prevRange * 0.5

// === 1MIN CONFIRMATION - THE KEY FILTER ===
// Get 1min pivot highs/lows from lower timeframe
// We check last 60 x 1min bars for equal highs/lows

// 1min pivot highs
ph1m = request.security(syminfo.tickerid, "1", ta.pivothigh(high, 2, 2), lookahead=barmerge.lookahead_off)
pl1m = request.security(syminfo.tickerid, "1", ta.pivotlow(low, 2, 2), lookahead=barmerge.lookahead_off)

// Store last two 1min pivots
var float last1mPH1 = na
var float last1mPH2 = na
var float last1mPL1 = na
var float last1mPL2 = na

if not na(ph1m)
    last1mPH2 := last1mPH1
    last1mPH1 := ph1m

if not na(pl1m)
    last1mPL2 := last1mPL1
    last1mPL1 := pl1m

// 1min Equal Highs: two 1min peaks within 5% of Prev Range AND near Prev High
equalHighs1m = not na(last1mPH1) and not na(last1mPH2) and math.abs(last1mPH1 - last1mPH2) <= prevRange * tol1 and math.abs(last1mPH1 - prevHigh1H) <= prevRange * 0.3
// 1min Equal Lows: two 1min bottoms within 5% AND near Prev Low
equalLows1m = not na(last1mPL1) and not na(last1mPL2) and math.abs(last1mPL1 - last1mPL2) <= prevRange * tol1 and math.abs(last1mPL1 - prevLow1H) <= prevRange * 0.3

// Plot 1min confirmation status on chart
plotshape(equalHighs1m, title="1m Equal Highs OK", location=location.top, color=color.new(color.orange, 0), style=shape.circle, size=size.tiny, text="1m EQ HIGH")
plotshape(equalLows1m, title="1m Equal Lows OK", location=location.bottom, color=color.new(color.orange, 0), style=shape.circle, size=size.tiny, text="1m EQ LOW")

// === FINAL STRATEGY 2 - ONLY IF 1min CONFIRMS ===
dtBreak = isDT_5m and equalHighs1m and close < neckDT
dbBreak = isDB_5m and equalLows1m and close > neckDB

plotshape(dtBreak, title="S2 DOUBLE TOP CONFIRMED", location=location.abovebar, color=color.new(color.red, 0), style=shape.triangledown, size=size.normal, text="S2 DT ✓")
plotshape(dbBreak, title="S2 DOUBLE BOTTOM CONFIRMED", location=location.belowbar, color=color.new(color.green, 0), style=shape.triangleup, size=size.normal, text="S2 DB ✓")

// === ALERTS ===
if sweepTop
    alert('{"pair": "' + syminfo.ticker + '", "strategy": "STRATEGY 1 - SWEEP", "direction": "SELL", "entry": "' + str.tostring(close) + '", "sl": "' + str.tostring(high) + '", "tp1": "' + str.tostring(midLine) + '", "tp2": "' + str.tostring(prevLow1H) + '", "prev_high": "' + str.tostring(prevHigh1H) + '", "prev_low": "' + str.tostring(prevLow1H) + '"}', alert.freq_once_per_bar)

if sweepBottom
    alert('{"pair": "' + syminfo.ticker + '", "strategy": "STRATEGY 1 - SWEEP", "direction": "BUY", "entry": "' + str.tostring(close) + '", "sl": "' + str.tostring(low) + '", "tp1": "' + str.tostring(midLine) + '", "tp2": "' + str.tostring(prevHigh1H) + '", "prev_high": "' + str.tostring(prevHigh1H) + '", "prev_low": "' + str.tostring(prevLow1H) + '"}', alert.freq_once_per_bar)

if dtBreak
    alert('{"pair": "' + syminfo.ticker + '", "strategy": "STRATEGY 2 - DOUBLE TOP + 1m CONFIRM", "direction": "SELL", "entry": "' + str.tostring(close) + '", "sl": "' + str.tostring(math.max(lastPH1, lastPH2)) + '", "tp1": "' + str.tostring(midLine) + '", "tp2": "' + str.tostring(prevLow1H) + '", "prev_high": "' + str.tostring(prevHigh1H) + '", "prev_low": "' + str.tostring(prevLow1H) + '"}', alert.freq_once_per_bar)

if dbBreak
    alert('{"pair": "' + syminfo.ticker + '", "strategy": "STRATEGY 2 - DOUBLE BOTTOM + 1m CONFIRM", "direction": "BUY", "entry": "' + str.tostring(close) + '", "sl": "' + str.tostring(math.min(lastPL1, lastPL2)) + '", "tp1": "' + str.tostring(midLine) + '", "tp2": "' + str.tostring(prevHigh1H) + '", "prev_high": "' + str.tostring(prevHigh1H) + '", "prev_low": "' + str.tostring(prevLow1H) + '"}', alert.freq_once_per_bar)
