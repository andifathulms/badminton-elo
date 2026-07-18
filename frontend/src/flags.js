// BWF uses 3-letter IOC country codes; flag emoji use ISO 3166-1 alpha-2.
// Map the badminton-playing nations, fall back to the raw code when unknown.
const IOC_TO_ISO2 = {
  CHN: 'CN', INA: 'ID', MAS: 'MY', JPN: 'JP', KOR: 'KR', DEN: 'DK', TPE: 'TW',
  THA: 'TH', IND: 'IN', HKG: 'HK', FRA: 'FR', GER: 'DE', ESP: 'ES', USA: 'US',
  CAN: 'CA', SGP: 'SG', VIE: 'VN', MYA: 'MM', NED: 'NL', RUS: 'RU', UKR: 'UA',
  IRL: 'IE', SWE: 'SE', FIN: 'FI', NOR: 'NO', POL: 'PL', CZE: 'CZ', SUI: 'CH',
  AUT: 'AT', BEL: 'BE', BUL: 'BG', EST: 'EE', ISR: 'IL', AUS: 'AU', NZL: 'NZ',
  BRA: 'BR', PER: 'PE', MEX: 'MX', GUA: 'GT', RSA: 'ZA', EGY: 'EG', ALG: 'DZ',
  NGR: 'NG', MRI: 'MU', SRI: 'LK', PAK: 'PK', BAN: 'BD', NEP: 'NP', MDV: 'MV',
  TUR: 'TR', POR: 'PT', ITA: 'IT', SLO: 'SI', SVK: 'SK', HUN: 'HU', LTU: 'LT',
  LAT: 'LV', GRE: 'GR', CRO: 'HR', ROU: 'RO', KAZ: 'KZ', UZB: 'UZ', AZE: 'AZ',
  MGL: 'MN', PHI: 'PH', CAM: 'KH', LAO: 'LA', BRU: 'BN', MAC: 'MO', GEO: 'GE',
  ARM: 'AM', CYP: 'CY', LUX: 'LU', ISL: 'IS', MLT: 'MT', UAE: 'AE', KSA: 'SA',
  QAT: 'QA', BHR: 'BH', KUW: 'KW', JOR: 'JO', LIB: 'LB', IRI: 'IR', TKM: 'TM',
  SEY: 'SC', UGA: 'UG', KEN: 'KE', TAN: 'TZ', ZAM: 'ZM', BOT: 'BW', GHA: 'GH',
  CIV: 'CI', CMR: 'CM', MAW: 'MW', MOZ: 'MZ', ANG: 'AO', NAM: 'NA', ZIM: 'ZW',
  SUR: 'SR', DOM: 'DO', JAM: 'JM', TTO: 'TT', BAR: 'BB', CUB: 'CU', CHI: 'CL',
  ARG: 'AR', COL: 'CO', ECU: 'EC', URU: 'UY', PAR: 'PY', BOL: 'BO', GUM: 'GU',
  FIJ: 'FJ', TAH: 'PF', VAN: 'VU', SOL: 'SB', PNG: 'PG', NCL: 'NC',
}
// Home-nation subdivision flags (render on modern platforms).
const SUBDIVISION = { ENG: '🏴󠁧󠁢󠁥󠁮󠁧󠁿', SCO: '🏴󠁧󠁢󠁳󠁣󠁴󠁿', WAL: '🏴󠁧󠁢󠁷󠁬󠁳󠁿' }

export function flag(code) {
  if (!code) return ''
  const c = code.toUpperCase()
  if (SUBDIVISION[c]) return SUBDIVISION[c]
  const iso = IOC_TO_ISO2[c]
  if (!iso) return ''
  return iso.replace(/./g, (ch) =>
    String.fromCodePoint(127397 + ch.charCodeAt(0)),
  )
}
