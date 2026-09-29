/* Sun and moon for the visitor's place and day. Formulas from SunCalc (Vladimir Agafonkin,
   BSD-2-Clause), trimmed to what the site needs. No DOM: runs in the page, the scene and Node. */

const RAD = Math.PI/180, DAY_MS = 864e5, J1970 = 2440588, J2000 = 2451545, E = RAD*23.4397;

const toDays = date => date.valueOf()/DAY_MS - 0.5 + J1970 - J2000;
const fromJulian = j => new Date((j + 0.5 - J1970)*DAY_MS);
const declination = (l, b) => Math.asin(Math.sin(b)*Math.cos(E) + Math.cos(b)*Math.sin(E)*Math.sin(l));
const rightAscension = (l, b) => Math.atan2(Math.sin(l)*Math.cos(E) - Math.tan(b)*Math.sin(E), Math.cos(l));
const meanAnomaly = d => RAD*(357.5291 + 0.98560028*d);
function eclipticLongitude(M){
  const C = RAD*(1.9148*Math.sin(M) + 0.02*Math.sin(2*M) + 0.0003*Math.sin(3*M));
  return M + C + RAD*102.9372 + Math.PI;
}

/** Sun elevation and azimuth in degrees (azimuth from south, positive to the west). */
export function sunPosition(date, lat, lon){
  const d = toDays(date), M = meanAnomaly(d), L = eclipticLongitude(M);
  const dec = declination(L, 0), ra = rightAscension(L, 0);
  const H = RAD*(280.16 + 360.9856235*d) + RAD*lon - ra, phi = RAD*lat;
  const el = Math.asin(Math.sin(phi)*Math.sin(dec) + Math.cos(phi)*Math.cos(dec)*Math.cos(H));
  const az = Math.atan2(Math.sin(H), Math.cos(H)*Math.sin(phi) - Math.tan(dec)*Math.cos(phi));
  return { el: el/RAD, az: az/RAD };
}

/** Sunrise and sunset (Date objects) for the day of `date`; null when the sun never crosses the horizon. */
export function sunTimes(date, lat, lon){
  const lw = -RAD*lon, phi = RAD*lat, d = toDays(date);
  const J0 = 0.0009, n = Math.round(d - J0 - lw/(2*Math.PI));
  const ds = J0 + lw/(2*Math.PI) + n;
  const M = meanAnomaly(ds), L = eclipticLongitude(M), dec = declination(L, 0);
  const transit = x => J2000 + x + 0.0053*Math.sin(M) - 0.0069*Math.sin(2*L);
  const noon = transit(ds);
  const cosW = (Math.sin(-0.833*RAD) - Math.sin(phi)*Math.sin(dec))/(Math.cos(phi)*Math.cos(dec));
  if (cosW < -1 || cosW > 1) return { rise: null, set: null, noon: fromJulian(noon) };
  const set = transit(J0 + (Math.acos(cosW) + lw)/(2*Math.PI) + n);
  return { rise: fromJulian(noon - (set - noon)), set: fromJulian(set), noon: fromJulian(noon) };
}

/** Moon phase: 0 new, 0.25 first quarter, 0.5 full, 0.75 last quarter. */
export function moonPhase(date){
  const synodic = 29.530588853, newMoon = Date.UTC(2000, 0, 6, 18, 14);
  const p = ((date.valueOf() - newMoon)/DAY_MS/synodic) % 1;
  return (p + 1) % 1;
}

/** The three offices, for the clocks at the bottom of the page. */
export const OFFICES = [
  { id: 'smi', tz: 'Europe/Rome', lat: 43.68, lon: 10.85, name: { it: 'San Miniato', en: 'San Miniato' } },
  { id: 'nyc', tz: 'America/New_York', lat: 40.71, lon: -74.01, name: { it: 'New York', en: 'New York' } },
  { id: 'sfo', tz: 'America/Los_Angeles', lat: 37.77, lon: -122.42, name: { it: 'San Francisco', en: 'San Francisco' } }
];
