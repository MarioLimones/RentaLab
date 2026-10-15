import { useEffect, useState } from 'react';
import { api, type PublicAvailabilityCalendar } from '../api/client';
import { isCalendarDate, todayInMadrid } from './dateRange';

interface CalendarState {
  key: string;
  scope: string;
  data: PublicAvailabilityCalendar | null;
  error: string | null;
  loading: boolean;
  canReachMonth: boolean;
}

function shiftMonth(month: string, offset: number): string {
  const date = new Date(`${month}-01T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + offset);
  return date.toISOString().slice(0, 7);
}

export function useAvailabilityCalendar(equipmentId: number, selectedDate: string, revision: number, checkFromStart = false) {
  const selectedMonth = isCalendarDate(selectedDate) ? selectedDate.slice(0, 7) : todayInMadrid().slice(0, 7);
  const anchor = selectedMonth > '9999-11' ? '9999-11' : selectedMonth < '0001-01' ? '0001-01' : selectedMonth;
  const [navigation, setNavigation] = useState<{ anchor: string; month: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const [state, setState] = useState<CalendarState>({ key: '', scope: '', data: null, error: null, loading: true, canReachMonth: false });
  const month = navigation && (!selectedDate || navigation.anchor === anchor) ? navigation.month : anchor;
  // Monthly occupancy is clipped. Check the preceding interval before offering a return in a later month.
  const bookingStart = checkFromStart && isCalendarDate(selectedDate) ? selectedDate : '';
  const prefixStart = checkFromStart && isCalendarDate(selectedDate) && selectedDate < `${month}-01` ? selectedDate : '';
  const scope = `${equipmentId}:${month}:${revision}:${retry}`;
  const key = `${scope}:${bookingStart}:${prefixStart}`;
  const current = state.key === key ? state : null;
  const monthData = state.scope === scope ? state.data : null;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    void Promise.resolve().then(async () => {
      if (!active) return;
      // Keep the same grid mounted while checking returns for a new pickup, preserving keyboard focus.
      setState((previous) => ({ key, scope, data: previous.scope === scope ? previous.data : null, error: null, loading: true, canReachMonth: false }));
      const [data, prefix] = await Promise.all([
        api.getPublicAvailabilityCalendar(equipmentId, { start_date: `${month}-01`, end_date: `${shiftMonth(month, 1)}-01`, ...(bookingStart ? { booking_start: bookingStart } : {}) }, controller.signal),
        prefixStart ? api.getPublicAvailability(equipmentId, { start_date: prefixStart, end_date: `${month}-01` }, controller.signal) : null,
      ]);
      if (active) setState({ key, scope, data, error: null, loading: false, canReachMonth: !prefix || prefix.available === true });
    }).catch((error: unknown) => {
      if (active) setState({ key, scope, data: null, error: error instanceof Error ? error.message : 'No se pudo cargar el calendario.', loading: false, canReachMonth: false });
    });
    return () => { active = false; controller.abort(); };
  }, [equipmentId, month, bookingStart, prefixStart, scope, key]);

  return {
    month, data: current?.data ?? monthData, error: current?.error ?? null, loading: !current || current.loading, canReachMonth: current?.canReachMonth ?? false,
    previous: () => setNavigation({ anchor, month: shiftMonth(month, -1) }),
    next: () => setNavigation({ anchor, month: shiftMonth(month, 1) }),
    goTo: (target: string) => {
      if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(target)) return;
      setNavigation({ anchor, month: target < '0001-01' ? '0001-01' : target > '9999-11' ? '9999-11' : target });
    },
    retry: () => setRetry((value) => value + 1),
  };
}
