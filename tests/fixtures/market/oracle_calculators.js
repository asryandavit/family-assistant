// Runs the forwarders' OWN calculator code (captured verbatim) over a grid of inputs and
// writes the answers as test oracles. No network: reads only the fixtures next to it.
//
//   node tests/fixtures/market/oracle_calculators.js
//
// Globbing: Calculator.prototype.calculate from globbing_calculator.js (sliced from its
//   app bundle) with the page globals (shippingConditions, customsLimitConverted,
//   customsWeightLimit, currencyEuroRate, mainCurrency, rates) from globbing_home_en.html.
// BuyForYou: calculateShipping() and its constants from buyforyou_home_hy.html, with the
//   page's own fallback eurRates (no fetch).
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const here = __dirname;

function between(s, start, end) {
  const i = s.indexOf(start);
  if (i < 0) throw new Error('marker not found: ' + start);
  const j = s.indexOf(end, i);
  return s.slice(i, j < 0 ? undefined : j);
}

// ---------------------------------------------------------------- Globbing
const gHtml = fs.readFileSync(path.join(here, 'globbing_home_en.html'), 'utf8');
const gCalc = fs.readFileSync(path.join(here, 'globbing_calculator.js'), 'utf8');
const gGlobals = ['shippingConditions', 'customsLimitConverted', 'customsWeightLimit',
                  'currencyEuroRate', 'mainCurrency', 'rates', 'calculatorLoyaltyMemberships'];
let gDecl = '';
for (const g of gGlobals) {
  const m = gHtml.match(new RegExp('let ' + g + ' = (.*?);\\s*\\n'));
  if (!m) throw new Error('global not found: ' + g);
  gDecl += 'var ' + g + ' = ' + m[1] + ';\n';
}

function field(v) { return { val: () => v }; }
function stubForm(inp) {
  const vals = {
    '.calculator-weight': inp.weight, '.calculator-price': inp.price || 0,
    '.calculator-currency': 10, '.weight-measurement': 'kg',
    '.calculator-width': inp.w || 0, '.calculator-height': inp.h || 0,
    '.calculator-length': inp.l || 0, '.calculator-measurement': 'cm',
  };
  const out = {};
  return {
    out,
    find: (sel) => {
      if (sel in vals) return field(vals[sel]);
      return {
        text: (t) => { out[sel] = t; },
        addClass: () => {}, removeClass: () => {}, val: () => '',
      };
    },
  };
}

const gCtx = { Math, parseInt, parseFloat, JSON, isNaN };
vm.createContext(gCtx);
// The page's setters only write text into the form; here they record it.
const gSetters = `
Calculator.prototype.setPrice = function (p) { this.form.find('.calculator__price--number').text(isNaN(p) ? 0 : p); };
Calculator.prototype.setShippingFee = function (p) { this.form.find('.shipping_fee--number').text(isNaN(p) ? 0 : p); };
Calculator.prototype.setCustomsFee = function (p) { this.form.find('.customs_fee--number').text(isNaN(p) ? 0 : p); };
`;
vm.runInContext(gDecl + gCalc + gSetters +
  '\nthis.Calculator = Calculator; this.shippingConditions = shippingConditions;', gCtx);

const weights = [0.05, 0.1, 0.5, 1.0, 1.003, 1.005, 1.008, 1.05, 2.4, 20, 30, 35];
const dims = [null, [60, 40, 30], [100, 50, 40]];
const prices = [0, 50000, 100000];   // declared value in AMD
const globbing = {};
for (const [id, cond] of Object.entries(gCtx.shippingConditions)) {
  for (const weight of weights) for (const d of dims) for (const price of prices) {
    // keep the grid small: prices only vary at 2.4 kg and 35 kg, dims only at price 0
    if (price && !(weight === 2.4 || weight === 35)) continue;
    if (d && price) continue;
    const inp = { weight, price, l: d ? d[0] : 0, w: d ? d[1] : 0, h: d ? d[2] : 0 };
    const form = stubForm(inp);
    const c = new gCtx.Calculator(form);
    c.shippingCondition = cond;
    c.calculate();
    const key = [id, weight, d ? d.join('x') : '', price].join('|');
    globbing[key] = {
      condition_id: Number(id), warehouse_id: cond.warehouse_id,
      method: cond.shipping_methods_id, input: inp,
      shipping: form.out['.shipping_fee--number'],
      customs: form.out['.customs_fee--number'],
      total: form.out['.calculator__price--number'],
    };
  }
}

// ---------------------------------------------------------------- BuyForYou
const bHtml = fs.readFileSync(path.join(here, 'buyforyou_home_hy.html'), 'utf8');
const bConsts = between(bHtml, 'const usdPrice', '// Currency API URL');
const bFallback = between(bHtml, 'eurRates = {', '}') + '};';
const bFn = between(bHtml, 'function calculateShipping()', '// 5. Toggle warning');
let bInputs = {};
const bCtx = {
  Math, parseFloat, console,
  document: { getElementById: (id) => (id in bInputs ? bInputs[id] : null) },
};
vm.createContext(bCtx);
vm.runInContext(bConsts + '\nvar ' + bFallback + '\n' + bFn +
  '\nreturn {shippingCost, customsFee, chargeableWeight};}\nthis.calc = calculateShipping;',
  bCtx);

const buyforyou = {};
for (const country of ['USA', 'China']) for (const method of ['air', 'sea']) {
  for (const weight of [0.05, 0.1, 0.3, 0.5, 1.0, 1.05, 2.4, 20]) for (const d of [null, [60, 40, 30], [61, 40, 30], [100, 50, 40]]) {
    for (const [cur, price] of [['AMD', 0], ['USD', 200], ['USD', 400], ['Yuan', 3000]]) {
      if (d && price) continue;
      if (price && weight !== 2.4) continue;
      const v = (x) => ({ value: String(x) });
      bInputs = {
        'calc-country-value': v(country), 'calc-weight-value': v('kg'), 'calc-dim-value': v('cm'),
        'calc-price-value': v(cur), 'calc-shipping-method-value': v(method),
        'calc-weight-val': v(weight), 'calc-height-val': v(d ? d[2] : 0),
        'calc-width-val': v(d ? d[1] : 0), 'calc-length-val': v(d ? d[0] : 0),
        'calc-price-val': v(price), volumetricWeightCheckbox: { checked: !!d },
      };
      const r = bCtx.calc();
      const key = [country, method, weight, d ? d.join('x') : '', cur, price].join('|');
      buyforyou[key] = { input: { country, method, weight, dims: d, currency: cur, price },
                         shipping: r.shippingCost, customs: r.customsFee,
                         chargeable_kg: r.chargeableWeight };
    }
  }
}

const meta = { captured: '2026-10-29', how: 'node oracle_calculators.js (forwarders\' own JS, no network)' };
fs.writeFileSync(path.join(here, 'globbing_calculator.json'),
  JSON.stringify({ _meta: meta, answers: globbing }, null, 1));
fs.writeFileSync(path.join(here, 'buyforyou_calculator.json'),
  JSON.stringify({ _meta: meta, answers: buyforyou }, null, 1));
console.log('globbing answers', Object.keys(globbing).length, '· buyforyou answers', Object.keys(buyforyou).length);
