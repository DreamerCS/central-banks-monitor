const sterlingFloor = 2.7780;

const decisions = {
  sep14: {
    effective: '10% prevailing base rate', pending: 'No increase announced',
    spot: 2.8131, age: 'Afternoon of 14 September. The Bank gives no exact minute.',
    text: 'Sterling rose after the Bundesbank cut its discount and Lombard rates. The smaller-than-anticipated cuts still left the UK authorities buying sterling in the market.'
  },
  sep15: {
    effective: '10% prevailing base rate', pending: 'No increase announced',
    spot: 2.7812, age: 'Closing quote on 15 September. The Bank gives no closing time.',
    text: 'Sterling weakened again. The Bank reports that many in the money market still thought a rate rise could wait upon the French referendum. This describes contemporary opinion, with no numerical survey probability.'
  },
  '0800': {
    effective: '10% prevailing base rate', pending: 'No increase announced',
    spot: 2.7794, age: '08:00 quote. No later intervention or rate decision enters this reading.',
    text: 'The latest price left little room before the bilateral floor. A small distance was enough to expose the Bank to intervention if selling continued. It said nothing certain about the authorities’ willingness to defend the floor.'
  },
  '1100': {
    effective: '12% minimum lending rate', pending: 'No further rise announced',
    quote: 'At the DM 2.7780 lower limit', age: 'Current at 11:00. The Bank reports the limit, without an individual transaction price.',
    text: 'With sterling at the boundary, the authorities set the minimum lending rate at 12%. The clearing banks subsequently raised their base rates. At the announcement the length of time the new 12% rate would apply was open.'
  },
  '1415': {
    effective: '12% minimum lending rate', pending: '15% from 17 September',
    quote: 'At the DM 2.7780 lower limit', age: 'Intraday account around the announcement. The report describes the limit and supplies no separately timestamped trade.',
    text: 'The 14:15 announcement specified the effective date. The Bank describes sterling at its limit as the decision was announced. An investor could price a possible rate increase alongside the risk of a change in the currency regime.'
  },
  '1930': {
    effective: '12% minimum lending rate', pending: '15% increase withdrawn',
    quote: 'At the limit at the close of EMS operations', age: 'Earlier that day. The record supplies no spot quote at the evening announcement.',
    text: 'Just after 19:30 the Chancellor suspended ERM participation and withdrew the next day’s proposed increase. After suspension the old intervention limit no longer bound the exchange rate.'
  },
  '0930': {
    effective: '10% minimum lending rate', pending: 'No 15% rate in force',
    quote: 'No 09:30 spot quote in this chronology', age: 'The previous day’s intervention limit ceased to apply on 16 September.',
    text: 'The Bank returned to dealing rates consistent with 10% at 09:30. Gilts up to ten years were in demand as investors anticipated lower short rates, while longer conventional gilts fell amid concerns about future inflation.'
  }
};

const picker = document.getElementById('erm-asof');
function showDecision() {
  const item = decisions[picker.value];
  document.getElementById('erm-effective').textContent = item.effective;
  document.getElementById('erm-pending').textContent = item.pending;
  const quote = item.spot == null ? item.quote :
    'DM ' + item.spot.toFixed(4) + ' per £ · ' + (100 * (item.spot / sterlingFloor - 1)).toFixed(3) + '% above limit';
  document.getElementById('erm-quote').textContent = quote;
  document.getElementById('erm-age').textContent = item.age;
  document.getElementById('erm-snapshot').textContent = item.text;
}
if (picker) {
  picker.addEventListener('change', showDecision);
  showDecision();
}
