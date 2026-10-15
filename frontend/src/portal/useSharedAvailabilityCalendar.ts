import { useEffect, useState } from 'react';
import { api, type PublicAvailabilityCalendar } from '../api/client';
import { isCalendarDate, todayInMadrid } from './dateRange';

function shiftMonth(month: string, offset: number) {
  const date = new Date(`${month}-01T12:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + offset);
  return date.toISOString().slice(0, 7);
}

/** A day is free only if every selected model can be hired for the whole interval. */
export function useSharedAvailabilityCalendar(equipmentIds: number[], selectedDate: string, revision: number) {
  const idsKey = equipmentIds.join(',');
  const selectedMonth = isCalendarDate(selectedDate) ? selectedDate.slice(0, 7) : todayInMadrid().slice(0, 7);
  const anchor = selectedMonth > '9999-11' ? '9999-11' : selectedMonth;
  const [navigation, setNavigation] = useState<{ anchor: string; month: string } | null>(null);
  const [retry, setRetry] = useState(0);
  const month = navigation && (!selectedDate || navigation.anchor === anchor) ? navigation.month : anchor;
  const bookingStart = isCalendarDate(selectedDate) ? selectedDate : '';
  const prefixStart = bookingStart && bookingStart < `${month}-01` ? bookingStart : '';
  const scope = `${idsKey}:${month}:${revision}:${retry}`;
  const key = `${scope}:${bookingStart}`;
  const [state, setState] = useState({ key: '', scope: '', data: null as PublicAvailabilityCalendar | null, error: null as string | null, loading: true, canReachMonth: false });
  const current = state.key === key ? state : null;
  const monthData = state.scope === scope ? state.data : null;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const ids = idsKey ? idsKey.split(',').map(Number) : [];
    void Promise.resolve().then(async () => {
      if (!active) return;
      setState((previous) => ({ key, scope, data: previous.scope === scope ? previous.data : null, error: null, loading: true, canReachMonth: false }));
      if (!ids.length) {
        setState({ key, scope, data: null, error: null, loading: false, canReachMonth: false });
        return;
      }
      const results = await Promise.all(ids.map(async (id) => {
        const [calendar, prefix] = await Promise.all([
          api.getPublicAvailabilityCalendar(id, { start_date: `${month}-01`, end_date: `${shiftMonth(month, 1)}-01`, ...(bookingStart ? { booking_start: bookingStart } : {}) }, controller.signal),
          prefixStart ? api.getPublicAvailability(id, { start_date: prefixStart, end_date: `${month}-01` }, controller.signal) : null,
        ]);
        return { calendar, prefix };
      }));
      if (active) setState({ key, scope, loading: false, error: null,
        canReachMonth: results.every(({ prefix }) => !prefix || prefix.available === true),
        data: { equipment_id: ids[0]!, start_date: `${month}-01`, end_date: `${shiftMonth(month, 1)}-01`,
          can_book: results.every(({ calendar }) => calendar.can_book),
          occupied_ranges: results.flatMap(({ calendar }) => calendar.occupied_ranges),
          unavailable_end_dates: [...new Set(results.flatMap(({ calendar }) => calendar.unavailable_end_dates ?? []))],
        },
      });
    }).catch((failure: unknown) => {
      if (active) setState({ key, scope, data: null, loading: false, canReachMonth: false, error: failure instanceof Error ? failure.message : 'No se pudo consultar el calendario conjunto.' });
    });
    return () => { active = false; controller.abort(); };
  }, [idsKey, month, bookingStart, prefixStart, scope, key]);

  return { month, data: current?.data ?? monthData, error: current?.error ?? null, loading: !current || current.loading, canReachMonth: current?.canReachMonth ?? false,
    previous: () => setNavigation({ anchor, month: shiftMonth(month, -1) }),
    next: () => setNavigation({ anchor, month: shiftMonth(month, 1) }),
    goTo: (target: string) => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(target)) setNavigation({ anchor, month: target < '0001-01' ? '0001-01' : target > '9999-11' ? '9999-11' : target }); },
    retry: () => setRetry((value) => value + 1),
  };
}
