"""Join policy publications to leadership, retrospective business cycles and pre-event rates.

Run after building the individual bank datasets. All inputs are versioned site files.
Optional --data and --bank accept an input directory and bank ids for local checks.
"""
import argparse
import bisect
import json
import math
from datetime import date, datetime, timedelta
from itertools import groupby
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
CHRONOLOGY_CHECKED = '2026-11-20'
GOV_FED = 'https://www.federalreserve.gov/aboutthefed/bios/board/boardmembership.htm'
GOV_ECB = 'https://www.ecb.europa.eu/ecb/decisions/eb/html/executive-board-terms-of-office.en.html'
NBER = 'https://www.nber.org/research/data/us-business-cycle-expansions-and-contractions'
EABCN = 'https://eabcn.org/dbc/peaksandtroughs/chronology-euro-area-business-cycles'
FED_MARKET = 'https://www.frbsf.org/research-and-insights/data-and-indicators/us-monetary-policy-event-study-database/'
ECB_MARKET = 'https://www.ecb.europa.eu/pub/pdf/other/Dataset_EA-MPD.xlsx'
METHOD = [
    'Each row is an official communication. Its wording score comes from the underlying text series. Leadership identifies the officeholder on the publication date. A committee statement expresses the committee’s view.',
    'The coverage denominator includes unscored publications. A missing score means that evidence is insufficient for a rate-direction reading. A score of zero is reserved for an explicit steady path or balanced forward assessment under the relevant bank’s rules.',
    'Same and opposite counts require a directional text score and an absolute market move exceeding one basis point. A positive market move raises the relevant expected rate or yield. Market data may be missing even when the text can be scored.',
    'The median absolute move describes the typical size of repricing regardless of sign. Columns use the observations with the relevant instrument. Central banks have different horizons and release windows. Conference and release observations can be filtered separately.',
    'Leadership and business-cycle summaries describe each sample. The composition of meetings, institutional practices, price availability and choice of instrument can differ substantially across groups. Small counts make comparisons particularly sensitive to individual releases.',
]
PHASE_METHOD = ('Difference between the domestic BIS benchmark policy rate on the last observed date on or before the day preceding the event '
                'and its level 180 calendar days earlier. Positive is tightening, negative is easing and zero is unchanged. '
                'The calculation requires both endpoints within seven days of their target dates, no internal observation gap above ten days '
                'and a comparable instrument at both ends. The measure covers policy rates only.')
TURNING_POINTS = {
    'fed': [('2001-03','2001-11'),('2007-12','2009-06'),('2020-02','2020-04')],
    'ecb': [('2008 Q1','2009 Q2'),('2011 Q3','2013 Q1'),('2019 Q4','2020 Q2')],
}
MARKETS = {
    'fed': ('Next-meeting fed funds futures (MP2)', 'Scheduled statement, −10 to +20 minutes', FED_MARKET),
    'ecb': ('1-year euro OIS', 'ECB policy release or press conference, as identified for each record', ECB_MARKET),
}
META = {
    'fed': ('Federal Reserve', 'US', 'fed-statement-stance.json', GOV_FED, NBER, 'NBER monthly chronology'),
    'ecb': ('European Central Bank', 'XM', 'ecb-stance-history.json', GOV_ECB, EABCN, 'EABCN quarterly chronology'),
}
CYCLE_METHOD = {
    'fed':'A contraction starts in the month following an NBER peak and ends in the trough month. The chronology is retrospective. Recent dates are classified against turning points published by the study cutoff.',
    'ecb':'A contraction starts in the quarter following an EABCN peak and includes the trough quarter. Meetings inherit the quarter’s classification. The committee dates euro-area activity retrospectively.',
}


def load(path):
    return json.loads(path.read_text())


def source(label, url):
    return {'label':label, 'url':url}


def quarter(day):
    return f'{day.year} Q{(day.month + 2) // 3}'


def cycle_at(bank, day):
    if day.isoformat() > CHRONOLOGY_CHECKED:
        return 'Unclassified'
    period = quarter(day) if bank == 'ecb' else day.isoformat()[:7]
    return ('Contraction' if any(peak < period <= trough for peak, trough in TURNING_POINTS[bank])
            else 'Outside dated contraction')


def leadership_terms(bank, folder):
    profiles = load(folder / (bank + '-leadership.json'))['profiles']
    return [(p['start'],p['name']) for p in profiles]


def label_tenure(terms, day):
    i = bisect.bisect_right([t[0] for t in terms],day) - 1
    if i < 0:
        raise ValueError('Unknown officeholder on '+day)
    return terms[i][1]


def daily_rates(start, series):
    dates, values = [], []
    for offset, count, value in series['observations']:
        dates.extend(range(start+offset,start+offset+count))
        values.extend([value]*count)
    if not all(a<b for a,b in zip(dates, dates[1:])):
        raise ValueError('Policy series is not chronological')
    return dates, values


def policy_phase(bank, day, rates):
    dates, values = rates
    end = day.toordinal()-1
    start = end-180
    i, j = (bisect.bisect_right(dates, q)-1 for q in (start,end))
    if i<0 or j<0 or start-dates[i]>7 or end-dates[j]>7:
        return None
    if any(b-a>10 for a,b in zip(dates[i:j],dates[i+1:j+1])):
        return None
    # Changes in rate definition would otherwise look like changes in the instrument.
    breaks = {'ecb':'2024-09-18','fed':'2008-12-16'}
    if dates[i] < date.fromisoformat(breaks[bank]).toordinal() <= dates[j]:
        return None
    return round(100*(values[j]-values[i]),4)


def classify(rate):
    if rate is None:
        return 'Unclassified'
    return 'Tightening' if rate>0 else 'Easing' if rate<0 else 'Unchanged'


def median_or_none(values):
    return round(median(values),4) if values else None


def market_sign(bp, band=1):
    if abs(bp)<band or math.isclose(abs(bp),band,abs_tol=1e-9,rel_tol=0):
        return 0
    return 1 if bp>0 else -1


def summary(rows, label):
    scored = [r['score'] for r in rows if r['score'] is not None]
    paired = [r for r in rows if r['score'] not in (None,0) and r['marketBp'] is not None]
    actionable = [r for r in paired if market_sign(r['marketBp']) != 0]
    quotes = [r['marketBp'] for r in rows if r['marketBp'] is not None]
    steps = [r['actionBp'] for r in rows if r['actionBp'] is not None]
    priors = [r for r in rows if r['priorMoveBp'] is not None]
    proxies = sum(r.get('priorIsProxy') is True for r in priors)
    prior_types = {(r.get('priorInstrumentKey'),r.get('priorIsProxy') is True) for r in priors}
    median_prior = median_or_none([r['priorMoveBp'] for r in priors]) if len(prior_types)==1 else None
    gaps = [r['pricingGapBp'] for r in rows if r.get('pricingGapBp') is not None]
    same = sum(r['score']*market_sign(r['marketBp'])>0 for r in actionable)
    shifts = [r['shift'] for r in rows if r['shift'] is not None]
    return dict(label=label,n=len(rows),scored=len(scored),hawkish=sum(v>0 for v in scored),
                dovish=sum(v<0 for v in scored),steady=scored.count(0),unscored=len(rows)-len(scored),
                marketN=len(quotes), medianMarketBp=median_or_none(quotes),
                medianAbsMarketBp=median_or_none([abs(q) for q in quotes]),
                pairedN=len(paired),comparable=len(actionable),same=same,opposite=len(actionable)-same,
                flatMarket=len(paired)-len(actionable), outsideBandN=sum(market_sign(q)!=0 for q in quotes),
                actionN=len(steps),medianActionBp=median_or_none(steps),
                priorN=len(priors),priorProxyN=proxies,priorNonProxyN=len(priors)-proxies,medianPriorMoveBp=median_prior,
                pricingGapN=len(gaps),medianPricingGapBp=median_or_none(gaps),medianAbsPricingGapBp=median_or_none([abs(v) for v in gaps]),
                tighterThanPrior=sum(market_sign(v)>0 for v in gaps),withinPriorBand=sum(market_sign(v)==0 for v in gaps),
                easierThanPrior=sum(market_sign(v)<0 for v in gaps),
                shiftN=len(shifts),hawkishShifts=sum(s>0 for s in shifts),dovishShifts=sum(s<0 for s in shifts))


def episode_at(bank, day):
    if cycle_at(bank,day) != 'Contraction':
        return None
    period = quarter(day) if bank == 'ecb' else day.isoformat()[:7]
    for first, last in TURNING_POINTS[bank]:
        if first < period and period <= last:
            return first + ' to ' + last
    raise ValueError('Missing contraction episode for '+day.isoformat())


def comparison_sample(sample):
    inside = [abs(r['marketBp']) for r in sample if r['cycle']=='Contraction']
    outside = [abs(r['marketBp']) for r in sample if r['cycle']=='Outside dated contraction']
    gap = median(inside)-median(outside) if inside and outside else None
    return dict(contractionN=len(inside),outsideN=len(outside),contractionMedianAbsBp=median_or_none(inside),
                outsideMedianAbsBp=median_or_none(outside),gapBp=None if gap is None else round(gap,4))


def cycle_comparison(rows):
    windows = []
    by_window = sorted((r for r in rows if r['marketBp'] is not None),
                       key=lambda r:(r['sourceType'], r['marketInstrument']))
    for (source_type, instrument), sub in groupby(by_window, key=lambda r:(r['sourceType'],r['marketInstrument'])):
        sample = list(sub)
        episodes = sorted(set(r['episode'] for r in sample if r['episode'] is not None))
        by_episode = []
        for episode in episodes:
            entries = [r for r in sample if r['episode']==episode]
            other = [r for r in sample if r['episode']!=episode]
            by_episode.append(dict(episode=episode,n=len(entries),
                                   medianAbsMarketBp=median_or_none([abs(r['marketBp']) for r in entries]),
                                   gapExcludingEpisodeBp=comparison_sample(other)['gapBp']))
        windows.append(dict(sourceType=source_type,marketInstrument=instrument,
                            sensitivity=sensitivity(sample),all=comparison_sample(sample),hold=comparison_sample([r for r in sample if r['actionBp']==0]),
                            episodes=by_episode))
    return dict(windows=windows,method='For each instrument and communication type, compare the median absolute window move inside and outside dated contractions. The difference is contraction minus outside. The hold check keeps only known zero policy-rate steps. Omitting each recession in turn shows how strongly the comparison depends on a single downturn. The sample supports descriptive comparisons. No causal effect is identified.')

def sensitivity(rows):
    paired = [r for r in rows if r['score'] not in (None,0) and r['marketBp'] is not None]
    cases = []
    for band in (0.5,1,2):
        signs = [market_sign(r['marketBp'],band) * r['score'] for r in paired]
        same = sum(s>0 for s in signs)
        opposite = sum(s<0 for s in signs)
        cases.append(dict(bandBp=band,pairedN=len(signs),insideBand=len(signs)-same-opposite,
                          comparable=same+opposite,same=same,opposite=opposite))
    return cases


def paired_windows(rows):
    pairs = []
    for r in rows:
        release = r.get('releaseReading')
        if r['sourceType'] != 'conference' or not release or r['marketBp'] is None or release.get('marketBp') is None:
            continue
        pairs.append((r,release))
    def compare(pairs,label):
        release_abs = [abs(release['marketBp']) for r,release in pairs]
        conference_abs = [abs(r['marketBp']) for r,release in pairs]
        gaps = [c - s for c,s in zip(conference_abs,release_abs)]
        texts = [(r['score'],release.get('score')) for r,release in pairs if r['score'] is not None and release.get('score') is not None]
        return dict(label=label,n=len(pairs),releaseMedianAbsBp=median_or_none(release_abs),
                    conferenceMedianAbsBp=median_or_none(conference_abs),pairedMedianGapBp=median_or_none(gaps),
                    conferenceLarger=sum(x>1e-9 for x in gaps),releaseLarger=sum(x < -1e-9 for x in gaps),
                    equal=sum(abs(x)<=1e-9 for x in gaps),bothScored=len(texts),
                    sameScore=sum(a==b for a,b in texts))
    result = dict(all=compare(pairs,'All matched meetings'),byCycle=[],byLeader=[])
    for field, dest in [('cycle','byCycle'),('leader','byLeader')]:
        for val in dict.fromkeys(r[field] for r,_ in pairs):
            result[dest].append(compare([pair for pair in pairs if pair[0][field]==val],val))
    result['method'] = ('Each meeting supplies two 1-year euro OIS changes, one around the decision release and one around the conference. '
                        'The paired gap is the median of the within-meeting difference in absolute moves (conference minus release). '
                        'The conference window spans a longer interval and may also include other news.')
    return result


def lag_month(day):
    serial = day.year*12 + day.month-1 - 2
    return f'{serial//12:04d}-{serial%12+1:02d}'


def decision_pricing(bank, row, instrument_source, clock):
    prior = row['priorMoveBp']
    if prior is None:
        return
    if not math.isfinite(prior):
        raise ValueError('Invalid priced policy move on '+row['date'])
    if bank == 'fed':
        row.update(priorInstrument='Current-meeting federal funds target change', priorInstrumentKey='FED_TARGET',
                   priorMethod='Reconstructed from the announced target change and the MP1 federal funds futures surprise.',
                   priorPricingAsOf=row['date'], priorPricingSource=FED_MARKET, priorApproximate=True, priorGapEligible=True, priorQuoteQualifier='point',
                   priorPricingDate=row['date']+' · scheduled FOMC statement window (−10 to +20 minutes)',
                   pricingGapSource=row['url'],
                   pricingGapMethod='Announced target change minus the reconstructed prior. By construction this equals the current-meeting MP1 surprise.')
        if clock:
            published = datetime.strptime(clock,'%H:%M')
            window = (published - timedelta(minutes=10)).strftime('%H:%M')+'–'+(published + timedelta(minutes=20)).strftime('%H:%M')
            row.update(releaseTimeET=clock,priorPricingDate=f"{row['date']} · {window} ET futures window around the {clock} ET statement")
    else:
        earlier = row.get('earlierPriorMoveBp')
        if earlier is not None:
            if not math.isfinite(earlier) or not row.get('earlierPriorDate') or not row.get('earlierPriorSource'):
                raise ValueError('Incomplete earlier pricing observation on '+row['date'])
            if row['earlierPriorDate'] >= row['date']:
                raise ValueError('Earlier observation is outside the pre-decision period on '+row['date'])
            row['priorRepricingBp'] = round(prior - earlier, 8)
        if row.get('priorInstrumentKey') != 'DFR' or row.get('priorGapEligible') is not True:
            return
        row.update(pricingGapSource=instrument_source,
                   pricingGapMethod='Announced deposit facility rate change minus the market-implied change for this decision, using the source’s pre-decision observation.')
    if row['actionBp'] is None:
        return
    row['pricingGapBp'] = round(row['actionBp'] - prior, 8)
    if bank == 'fed' and not math.isclose(row['pricingGapBp'], row['currentSurpriseBp'], abs_tol=1e-7):
        raise ValueError('Reconstructed current-meeting surprise mismatch on '+row['date'])


def build_bank(bank, folder, rates_bundle):
    label, code, filename, leaders, dating, cycle_label = META[bank]
    raw = load(folder / filename)
    terms = leadership_terms(bank,folder)
    macro = load(folder / ('cycle-context.json' if bank=='fed' else 'euro-cycle-context.json'))
    macro_rows = {r['month']:r for r in macro['rows']}
    inflation_label = 'US all-items CPI (seasonally adjusted), 12-month change' if bank=='fed' else 'Euro-area all-items HICP, 12-month change'
    macro_sources = [source(inflation_label,macro['series']['cpiYoY']['sourceUrl']),
                     source('Unemployment rate',macro['series']['unemployment']['sourceUrl'])]
    benchmark = next(r for r in rates_bundle['series'] if r['id']==code)
    rates = daily_rates(date.fromisoformat(rates_bundle['start']).toordinal(),benchmark)
    quotes, clocks = {}, {}
    if bank=='fed':
        val = load(folder / 'stance-validation.json')
        quotes = {r['date']:r for r in val['expectations']['observations']}
        timing = load(folder/'fed-direction-study.json')
        timing_rows = [dict(zip(timing['fields'],entry)) for entry in timing['rows']]
        clocks = {event['date']:event['releaseTimeET'] for event in timing_rows if event['scheduled'] and event['releaseTimeET']}
    market, window, market_url = MARKETS[bank]
    rows = []
    for r in raw['records']:
        ds = r['date']
        day = date.fromisoformat(ds)
        if not ('2000-01-01' <= ds <= rates_bundle['through']):
            continue
        estimate = quotes.get(ds,{})
        net = policy_phase(bank, day, rates)
        reading = estimate.get('nextRepricingBp') if bank=='fed' else r.get('marketBp')
        src = r.get('sourceUrl') or r.get('url')
        if not src or not src.startswith('https://'):
            raise ValueError('Missing source on '+ds)
        row = dict(date=ds, leader=label_tenure(terms,ds), cycle=cycle_at(bank,day),
                   episode=episode_at(bank,day),policyPhase=classify(net),policyChangeBp=net,score=r['score'],shift=r.get('shift'),
                   previousDate=r.get('previousDate'),actionBp=r.get('actionBp'),marketBp=reading,
                   priorMoveBp=estimate.get('impliedPriorMoveBp',r.get('priorMoveBp')),
                   currentSurpriseBp=estimate.get('currentSurpriseBp',r.get('currentSurpriseBp')),
                   url=src,evidence=r.get('evidence'),rationale=r.get('rationale'),rule=r.get('rule'),
                   title=r.get('title'),sourceType=r.get('sourceType') or 'release',
                   marketInstrument=r.get('marketInstrument') or market,marketWindow=r.get('marketWindow') or window)
        context_month = lag_month(day)
        context = macro_rows.get(context_month,{})
        row.update(contextMonth=context_month,inflationYoY=context.get('cpiYoY'),unemploymentPct=context.get('unemployment'))
        raw_url = r.get('marketSource') or market_url
        if isinstance(raw_url,dict):
            raw_url = raw_url.get('url')
        row['marketUrl'] = raw_url
        for k in ['riskSignal','riskEvidence','instrument','topic','actionInstrument','actionLabel','publicationET','priorStart','priorEnd','releaseMeasures','marketMeasures','releaseReading','releaseUrl','evidenceKind','effectiveDate']:
            if r.get(k) is not None:
                row[k] = r[k]
        if bank=='ecb':
            row.update({k:v for k,v in r.items() if k.startswith(('prior','earlierPrior')) and v is not None})
        if estimate:
            for field in ['priorStart','priorEnd','prior2yBp','prior2s10sBp','yieldBp']:
                if estimate.get(field) is not None:
                    row[field] = estimate[field]
        decision_pricing(bank,row,raw.get('depositSource'),clocks.get(ds))
        if row['score'] not in [None,-2,-1,0,1,2]:
            raise ValueError('Unexpected score on '+ds)
        rows.append(row)
    rows.sort(key=lambda r:r['date'])
    if len(set(r['date'] for r in rows)) != len(rows):
        raise ValueError('Multiple primary records share a date for '+bank)
    if not rows:
        raise ValueError('No records in requested period for '+bank)
    groups = {}
    for field in ['leader','cycle','policyPhase','sourceType']:
        groups[field] = [summary([r for r in rows if r[field]==value],value)
                         for value in dict.fromkeys(r[field] for r in rows)]
    by_leader_cycle = []
    for leader in dict.fromkeys(r['leader'] for r in rows):
        cohort = [r for r in rows if r['leader']==leader]
        for cycle in dict.fromkeys(r['cycle'] for r in cohort):
            sub = [r for r in cohort if r['cycle']==cycle]
            by_leader_cycle.append(dict(leader=leader,cycle=cycle,**summary(sub,leader+' · '+cycle)))
    groups['leaderCycle'] = by_leader_cycle
    gov_sources = [source('Official terms of office',leaders)]
    if bank=='ecb':
        gov_sources.append(source('November 2003 handover','https://www.ecb.europa.eu/press/pr/date/2003/html/pr031101.en.html'))
    cycles = [source(cycle_label,dating)]
    price_sources = list(dict.fromkeys(r['marketUrl'] for r in rows if r['marketUrl']))
    if price_sources and bank!='fed':
        market_url = price_sources[0]
    bank_data = dict(id=bank,label=label,leaderSources=gov_sources,cycleSources=cycles,cycleLabel=cycle_label,
                macroSources=macro_sources,inflationLabel=inflation_label,
                macroMethod=('Inflation and unemployment describe the observation month two calendar months before the meeting, using data available at the study cutoff. Subsequent revisions can alter that history. ' + ('US CPI measures consumer prices on a different basis from the PCE price index used for the Fed’s inflation goal.' if bank=='fed' else 'Eurostat measures headline inflation using the all-items HICP.')),
                cycleMethod=CYCLE_METHOD[bank],policyPhaseMethod=PHASE_METHOD,policySource=benchmark['source'],
                marketLabel=market,marketWindow=window,marketUrl=market_url,marketSource=market_url,
                marketMethod='A positive market move signals a higher expected rate or yield for the specified horizon. A move within ±1 bp is inside the display band.',
                records=rows,groups=groups,all=summary(rows,'All publications'),cycleComparison=cycle_comparison(rows))
    if bank=='ecb':
        bank_data['pairedWindows'] = paired_windows(rows)
    return bank_data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'dist/data')
    parser.add_argument('--out',type=Path)
    parser.add_argument('--bank',dest='banks',choices=META,action='append')
    args = parser.parse_args()
    data = args.data
    rates = load(data/'historical-series.json')
    banks = [build_bank(b,data,rates) for b in (args.banks or META)]
    output = dict(schemaVersion=1,asOf=rates['through'],chronologyChecked=CHRONOLOGY_CHECKED,banks=banks,method=METHOD,
                  policyPhaseMethod=PHASE_METHOD,marketBandBp=1)
    dest=args.out or data/'stance-cohorts.json'
    dest.write_text(json.dumps(output,ensure_ascii=False,separators=(',',':'))+'\n')
    for bank in banks: print(bank['id'],bank['all'])


if __name__=='__main__':
    main()
