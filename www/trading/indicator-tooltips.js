/* indicator-tooltips.js — شرح كل المؤشرات بالعربي عند hover */
(function(){
const TIPS = {
  'RSI': {
    title: 'RSI (14)',
    desc: 'مؤشر القوة النسبية — يقيس سرعة وحجم تغيرات السعر.',
    vals: '< 30 = تشبع بيعي (فرصة شراء محتملة) | > 70 = تشبع شرائي (حذر) | 40-60 = منطقة محايدة'
  },
  'MACD': {
    title: 'MACD (12/26/9)',
    desc: 'مؤشر التقارب والتباعد — يقيس الفرق بين متوسطين متحركين. يكشف اتجاه الزخم وقوته.',
    vals: 'صاعد = الزخم يتحسن | هابط = الزخم يضعف | تقاطع صعودي = إشارة شراء | تقاطع هبوطي = إشارة بيع'
  },
  'EMA': {
    title: 'EMA (9/20/50/200)',
    desc: 'المتوسط المتحرك الأسي — يتبع الاتجاه. لما المتوسطات مرتبة (9>20>50) = اتجاه صاعد قوي.',
    vals: 'تقاطع ذهبي (Golden) = EMA9 فوق EMA20 = صاعد | تقاطع الموت (Death) = EMA9 تحت EMA20 = هابط'
  },
  'ADX': {
    title: 'ADX (14) — مؤشر قوة الاتجاه',
    desc: 'يقيس قوة الاتجاه الحالي (صاعد أو هابط). لا يحدد الاتجاه — فقط يقولك هل الاتجاه قوي أو ضعيف. مهم جداً لتحديد نظام السوق.',
    vals: '0-15 = لا اتجاه (سوق نائم — لا تدخل) | 15-20 = اتجاه ضعيف جداً (راقب فقط) | 20-25 = اتجاه يتشكّل (استعد) | 25-35 = اتجاه قوي ✅ (ادخل مع الاتجاه) | 35-50 = اتجاه قوي جداً (ممتاز بس قد يكون قرب النهاية) | > 50 = اتجاه متطرف (نادر — توقع انعكاس) | ⚡ النظام يستخدمه: ADX ≥ 25 → سوق اتجاهي (يخفف شروط الدخول) | ADX < 20 → سوق عرضي (يشدد الشروط +10 نقاط)'
  },
  'Stoch': {
    title: 'Stochastic K/D — مؤشر التشبع السريع',
    desc: 'يقارن سعر الإغلاق الحالي بأعلى وأدنى سعر خلال آخر 14 فترة. أسرع من RSI بكشف التشبع. K = الخط السريع، D = المتوسط البطيء.',
    vals: '0-20 = تشبع بيعي شديد ✅ (السهم مضغوط — فرصة ارتداد) | 20-30 = تشبع بيعي (مراقبة) | 30-70 = منطقة محايدة (لا إشارة) | 70-80 = تشبع شرائي (حذر) | 80-100 = تشبع شرائي شديد ⚠️ (تصحيح محتمل) | ⚡ إشارة شراء: K يعبر فوق D وهم تحت 20 | ⚡ إشارة بيع: K يعبر تحت D وهم فوق 80 | 🏆 في نظامك: Stoch < 20 من أقوى الأنماط الناجحة على أسهم الكويت'
  },
  'Vol': {
    title: 'Volume Ratio',
    desc: 'نسبة الحجم — حجم التداول الحالي مقارنة بمتوسط آخر 20 يوم. الحجم يؤكد الحركة.',
    vals: '< 0.5x = حجم ضعيف جداً | 1x = طبيعي | > 1.5x = اهتمام متزايد | > 2x = حجم قوي (تأكيد)'
  },
  'ATR': {
    title: 'ATR (14)',
    desc: 'متوسط المدى الحقيقي — يقيس تذبذب السهم اليومي. يُستخدم لحساب وقف الخسارة.',
    vals: 'ATR عالي = السهم يتحرك كثير (مخاطرة أعلى + فرصة أكبر) | ATR منخفض = السهم هادئ (ضغط قبل انفجار محتمل)'
  },
  'BB': {
    title: 'Bollinger Bands Squeeze — مؤشر الضغط والانفجار',
    desc: 'أشرطة بولينجر تقيس التذبذب — لما تضيق (Squeeze) يعني السهم هادئ ويستعد لحركة كبيرة. الـ Bandwidth يقيس عرض الأشرطة.',
    vals: 'Squeeze = TRUE ✅ → الأشرطة ضيقة جداً = انفجار سعري قادم (أهم إشارة!) | Squeeze = FALSE → الأشرطة عادية أو واسعة | Bandwidth < 5% = ضغط شديد (حركة كبيرة وشيكة) | Bandwidth 5-15% = تذبذب طبيعي | Bandwidth > 20% = تذبذب عالي (السهم يتحرك كثير) | ⚡ أفضل استخدام: Squeeze + Volume عالي = اختراق حقيقي | ⚡ حذر: Squeeze بدون حجم = اختراق كاذب محتمل | 🏆 في بورصة الكويت: كثير أسهم تضغط أسابيع ثم تنفجر بحركة سريعة'
  },
  'S/R': {
    title: 'Support / Resistance',
    desc: 'الدعم والمقاومة — مستويات سعرية ارتد منها السهم عدة مرات. الدعم = أرضية، المقاومة = سقف.',
    vals: 'قرب الدعم = فرصة شراء محتملة | قرب المقاومة = حذر من البيع | اختراق المقاومة = إشارة قوية | كسر الدعم = خطر'
  },
  'Confluence': {
    title: 'Confluence Score',
    desc: 'درجة التوافق — كم مؤشر يتفق على نفس الاتجاه. كل ما زادت الدرجة = الإشارة أقوى.',
    vals: '< 30 = ضعيف | 30-50 = متوسط | 50-70 = جيد | > 70 = قوي جداً | 100 = كل المؤشرات متفقة'
  },
  'R/R': {
    title: 'Risk/Reward Ratio',
    desc: 'نسبة العائد للمخاطرة — كم تربح مقابل كل 1 تخسره. أهم رقم بالتداول.',
    vals: '< 1.5x = ضعيف (لا تدخل) | 1.5-2x = مقبول | 2-3x = جيد | > 3x = ممتاز'
  },
  'Win%': {
    title: 'Win Rate',
    desc: 'نسبة النجاح التاريخية — من كل X مرة حصل هالنمط، كم مرة نجح فعلاً.',
    vals: '< 40% = ضعيف | 40-55% = متوسط | 55-70% = جيد | > 70% = ممتاز'
  },
  'Entry': {
    title: 'Entry Zone',
    desc: 'منطقة الدخول — النطاق السعري المثالي للشراء. محسوبة من الدعم + ATR.',
    vals: 'السعر داخل المنطقة = ادخل | فوق المنطقة = انتظر pullback | تحت المنطقة = كسر دعم (حذر)'
  },
  'Stop': {
    title: 'Stop Loss',
    desc: 'وقف الخسارة — السعر اللي تبيع عنده إذا السهم راح ضدك. يحمي رأس مالك.',
    vals: 'محسوب من: الدعم - (0.6 × ATR) | لا تتداول بدون وقف خسارة أبداً'
  },
  'Target': {
    title: 'Target Price',
    desc: 'السعر المستهدف — أقرب مقاومة أو متوسط الربح التاريخي للنمط.',
    vals: 'هدف 1 = أقرب مقاومة (جني أرباح جزئي) | هدف 2 = المقاومة التالية أو الربح التاريخي'
  },
  'Regime': {
    title: 'Market Regime',
    desc: 'نظام السوق — هل السوق اتجاهي (يتحرك بوضوح) أو عرضي (بدون اتجاه واضح).',
    vals: 'اتجاهي (ADX>25) = تتبع الاتجاه | عرضي (ADX<20) = ارتداد من الدعم/المقاومة | انتقالي = السوق يتغير'
  },
  'Confidence': {
    title: 'Confidence Score',
    desc: 'درجة الثقة — مبنية على 6 عوامل: تطابق النمط + نسبة النجاح + حجم العينة + جودة النمط + متوسط الربح + توافق شخصية السهم.',
    vals: '< 65 = ما يظهر | 65-70 = مراقبة | 70-80 = مرشح | > 80 = فرصة ذهبية'
  },
};

/* Helper function to wrap any text with tooltip */
window.indTip = function(key, text, extraVals) {
  var t = TIPS[key];
  if (!t) return text || key;
  var html = '<span class="ind-tip">' + (text || key);
  html += '<span class="tip-box">';
  html += '<div class="tip-title">' + t.title + '</div>';
  html += '<div class="tip-desc">' + t.desc + '</div>';
  var v = extraVals || t.vals;
  if (v) html += '<div class="tip-vals">' + v.replace(/\|/g, '<br>').replace(/([<>≥≤=]?\s*\d+[.x%]*)/g, '<span>$1</span>') + '</div>';
  html += '</span></span>';
  return html;
};

/* Auto-apply tooltips to elements with data-tip attribute */
/* Usage: <span data-tip="RSI">RSI 28</span> */
function autoTips() {
  document.querySelectorAll('[data-tip]').forEach(function(el) {
    if (el.classList.contains('ind-tip')) return;
    var key = el.getAttribute('data-tip');
    var t = TIPS[key];
    if (!t) return;
    el.classList.add('ind-tip');
    var box = document.createElement('span');
    box.className = 'tip-box';
    box.innerHTML = '<div class="tip-title">' + t.title + '</div>'
      + '<div class="tip-desc">' + t.desc + '</div>'
      + '<div class="tip-vals">' + (t.vals||'').replace(/\|/g, '<br>').replace(/([<>≥≤=]?\s*\d+[.x%]*)/g, '<span>$1</span>') + '</div>';
    el.appendChild(box);
  });
}

/* Run on load and after any dynamic content */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', autoTips);
} else {
  autoTips();
}

/* Re-run periodically for dynamic content */
setInterval(autoTips, 3000);
})();
