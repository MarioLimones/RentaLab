export type UserRole = 'customer' | 'admin';

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  active: boolean;
}

export interface RegisterInput {
  name: string;
  email: string;
  password: string;
}

export interface AuthSession {
  authenticated: true;
  username: string;
  expires_at: string;
  role: UserRole;
  user: User | null;
}

export interface LoginInput {
  username: string;
  password: string;
}

export interface Equipment {
  id: number;
  code: string;
  name: string;
  category: string;
  description: string;
  public_description?: string;
  technical_specs?: Record<string, string>;
  image_url?: string | null;
  active: boolean;
}

export type EquipmentInput = Omit<Equipment, 'id'>;
export type EquipmentPatch = Partial<EquipmentInput>;

export type ReservationStatus = 'confirmed' | 'cancelled';
export type ReservationOrigin = 'portal' | 'admin' | 'csv' | 'legacy';

export interface Reservation {
  id: number;
  equipment_id: number;
  customer_name: string;
  customer_email: string;
  start_date: string;
  end_date: string;
  status: ReservationStatus;
  external_reference: string | null;
  customer_user_id?: number | null;
  origin?: ReservationOrigin;
}

export type ReservationInput = Omit<Reservation, 'id' | 'status' | 'external_reference' | 'customer_user_id' | 'origin'> & {
  external_reference?: string | null;
};

export interface ReservationFilters {
  equipment_id?: number;
  status?: ReservationStatus;
  start_date?: string;
  end_date?: string;
  customer?: string;
  customer_user_id?: number;
  origin?: ReservationOrigin;
}

export interface DateRange {
  start_date: string;
  end_date: string;
}

export interface PublicEquipment {
  id: number;
  name: string;
  category: string;
  public_description: string;
  technical_specs: Record<string, string>;
  image_url: string | null;
  image_fallback_url: string;
  active_reservations_count: number;
}

export interface PublicEquipmentFilters {
  q?: string;
  category?: string;
}

export type PublicAvailability = { equipment_id: number } & (
  { status: 'select_dates'; start_date: null; end_date: null; available: null }
  | (DateRange & { status: 'available'; available: true })
  | (DateRange & { status: 'unavailable'; available: false })
);

export interface PublicAvailabilityCalendar extends DateRange {
  equipment_id: number;
  occupied_ranges: DateRange[];
  can_book: boolean;
  unavailable_end_dates?: string[];
}

export interface PublicReservationDates {
  equipment_id: number;
  reservations: DateRange[];
}

export interface CustomerReservation extends DateRange {
  id: number;
  equipment_id: number;
  status: ReservationStatus;
}

export interface CustomerReservationInput extends DateRange {
  equipment_id: number;
}

export interface SavedProducts {
  equipment_ids: number[];
}

export interface CustomerBatchReservationInput extends DateRange {
  equipment_ids: number[];
}

export interface CustomerIncident {
  id: number;
  reservation_id: number;
  title: string;
  description: string;
  status: IncidentStatus;
  public_response: string;
}

export interface CustomerIncidentInput {
  title: string;
  description: string;
}

export interface Availability extends DateRange {
  equipment_id: number;
  available: boolean;
  reason: 'equipment_inactive' | 'reservation_overlap' | 'blocking_incident' | null;
  conflicting_reservation_ids: number[];
}

export type IncidentPriority = 'low' | 'medium' | 'high';
export type IncidentStatus = 'open' | 'in_progress' | 'resolved';

export interface Incident {
  id: number;
  equipment_id: number;
  title: string;
  description: string;
  priority: IncidentPriority;
  blocking: boolean;
  status: IncidentStatus;
  resolution: string;
  confirmed_reservation_ids: number[];
  warning: string | null;
  reservation_id?: number | null;
  author_user_id?: number | null;
  public_response?: string;
  internal_notes?: string;
}

export interface IncidentInput {
  equipment_id: number;
  title: string;
  description?: string;
  priority?: IncidentPriority;
  blocking?: boolean;
}

export interface IncidentFilters {
  equipment_id?: number;
  status?: IncidentStatus;
  priority?: IncidentPriority;
  blocking?: boolean;
}

export interface IncidentStatusChange {
  status: IncidentStatus;
  resolution?: string | null;
}

export interface IncidentUpdate {
  priority?: IncidentPriority;
  blocking?: boolean;
  public_response?: string;
  internal_notes?: string;
}

export type ImportRowStatus = 'accepted' | 'already_imported' | 'rejected';

export type ImportRowResult = {
  line: number;
  external_reference: string | null;
  message: string;
} & (
  { status: Exclude<ImportRowStatus, 'rejected'>; reservation: Reservation }
  | { status: 'rejected'; reservation: null }
);

export interface ImportTotals {
  total: number;
  accepted: number;
  already_imported: number;
  rejected: number;
}

export interface ImportReport {
  totals: ImportTotals;
  rows: ImportRowResult[];
}

