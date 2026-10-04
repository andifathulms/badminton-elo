// Flag colours per IOC code — used for the nation ring around avatars, so a
// glance tells you the country. Order follows the flag (main colour first).
const C = {
  CHN: ['#DE2910', '#FFDE00'], INA: ['#CE1126', '#FFFFFF'], MAS: ['#CC0001', '#FFFFFF', '#010066', '#FFCC00'],
  JPN: ['#BC002D', '#FFFFFF'], KOR: ['#CD2E3A', '#FFFFFF', '#0047A0'], DEN: ['#C8102E', '#FFFFFF'],
  TPE: ['#FE0000', '#000095', '#FFFFFF'], THA: ['#A51931', '#F4F5F8', '#2D2A4A'], IND: ['#FF9933', '#FFFFFF', '#138808'],
  HKG: ['#DE2910', '#FFFFFF'], FRA: ['#0055A4', '#FFFFFF', '#EF4135'], GER: ['#000000', '#DD0000', '#FFCC00'],
  ESP: ['#AA151B', '#F1BF00'], USA: ['#B22234', '#FFFFFF', '#3C3B6E'], CAN: ['#D80621', '#FFFFFF'],
  SGP: ['#EF3340', '#FFFFFF'], VIE: ['#DA251D', '#FFFF00'], MYA: ['#FECB00', '#34B233', '#EA2839'],
  NED: ['#AE1C28', '#FFFFFF', '#21468B'], RUS: ['#FFFFFF', '#0039A6', '#D52B1E'], UKR: ['#0057B7', '#FFD700'],
  IRL: ['#169B62', '#FFFFFF', '#FF883E'], SWE: ['#006AA7', '#FECC00'], FIN: ['#FFFFFF', '#002F6C'],
  NOR: ['#BA0C2F', '#FFFFFF', '#00205B'], POL: ['#FFFFFF', '#DC143C'], CZE: ['#FFFFFF', '#D7141A', '#11457E'],
  SUI: ['#DA291C', '#FFFFFF'], AUT: ['#ED2939', '#FFFFFF'], BEL: ['#000000', '#FDDA24', '#EF3340'],
  BUL: ['#FFFFFF', '#00966E', '#D62612'], EST: ['#0072CE', '#000000', '#FFFFFF'], ISR: ['#FFFFFF', '#0038B8'],
  AUS: ['#00008B', '#FFFFFF', '#FF0000'], NZL: ['#00247D', '#FFFFFF', '#CC142B'], BRA: ['#009C3B', '#FFDF00', '#002776'],
  PER: ['#D91023', '#FFFFFF'], MEX: ['#006847', '#FFFFFF', '#CE1126'], GUA: ['#4997D0', '#FFFFFF'],
  RSA: ['#007749', '#FFB81C', '#001489', '#E03C31'], EGY: ['#CE1126', '#FFFFFF', '#000000'], ALG: ['#006233', '#FFFFFF', '#D21034'],
  NGR: ['#008751', '#FFFFFF'], MRI: ['#EA2839', '#1A206D', '#FFD500', '#00A551'], SRI: ['#8D153A', '#FFBE29', '#00534E'],
  PAK: ['#01411C', '#FFFFFF'], BAN: ['#006A4E', '#F42A41'], NEP: ['#DC143C', '#003893'],
  TUR: ['#E30A17', '#FFFFFF'], POR: ['#006600', '#FF0000'], ITA: ['#009246', '#FFFFFF', '#CE2B37'],
  SLO: ['#FFFFFF', '#005DA4', '#ED1C24'], SVK: ['#FFFFFF', '#0B4EA2', '#EE1C25'], HUN: ['#CE2939', '#FFFFFF', '#477050'],
  LTU: ['#FDB913', '#006A44', '#C1272D'], LAT: ['#9E3039', '#FFFFFF'], GRE: ['#0D5EAF', '#FFFFFF'],
  CRO: ['#FF0000', '#FFFFFF', '#171796'], ROU: ['#002B7F', '#FCD116', '#CE1126'], KAZ: ['#00AFCA', '#FEC50C'],
  UZB: ['#0099B5', '#FFFFFF', '#1EB53A'], AZE: ['#00B5E2', '#EF3340', '#509E2F'], MGL: ['#C4272F', '#015197'],
  PHI: ['#0038A8', '#CE1126', '#FCD116'], CAM: ['#032EA1', '#E00025'], BRU: ['#F7E017', '#FFFFFF', '#000000'],
  MAC: ['#00785E', '#FFFFFF'], ENG: ['#FFFFFF', '#CE1124'], SCO: ['#005EB8', '#FFFFFF'], WAL: ['#00B140', '#FFFFFF', '#C8102E'],
  UAE: ['#00732F', '#FFFFFF', '#000000', '#FF0000'], IRI: ['#239F40', '#FFFFFF', '#DA0000'], UGA: ['#000000', '#FCDC04', '#D90000'],
  KEN: ['#000000', '#BB0000', '#006600'], GHA: ['#CE1126', '#FCD116', '#006B3F'], CMR: ['#007A5E', '#CE1126', '#FCD116'],
  JAM: ['#009B3A', '#FED100', '#000000'], CUB: ['#002A8F', '#FFFFFF', '#CF142B'], ARG: ['#74ACDF', '#FFFFFF'],
  CHI: ['#0039A6', '#FFFFFF', '#D52B1E'], COL: ['#FCD116', '#003893', '#CE1126'], DOM: ['#002D62', '#FFFFFF', '#CE1126'],
  FIJ: ['#68BFE5', '#FFFFFF'], SEY: ['#003F87', '#FCD856', '#D62828', '#007A3D'], ZAM: ['#198A00', '#DE2010', '#000000', '#EF7D00'],
  SEN: ['#00853F', '#FDEF42', '#E31B23'], BOL: ['#D52B1E', '#F9E300', '#007934'], VEN: ['#FFCC00', '#00247D', '#CF142B'],
  CRC: ['#002B7F', '#FFFFFF', '#CE1126'], ECU: ['#FFDD00', '#034EA2', '#ED1C24'], ISL: ['#02529C', '#FFFFFF', '#DC1E35'],
  CYP: ['#FFFFFF', '#D57800'], LUX: ['#ED2939', '#FFFFFF', '#00A1DE'], MLT: ['#FFFFFF', '#CF142B'],
}
const NEUTRAL = ['#8A958F', '#C5CCC8']

export const nationColors = (code) => C[(code || '').toUpperCase()] || NEUTRAL

// conic-gradient ring for a nation (equal segments, starting at 12 o'clock).
export function nationRing(code) {
  const c = nationColors(code)
  const n = c.length
  return `conic-gradient(from -90deg, ${c.map((x, i) => `${x} ${(i * 100) / n}% ${((i + 1) * 100) / n}%`).join(', ')})`
}
