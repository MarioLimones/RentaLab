export type RolUsuario = 'customer' | 'admin';

export interface Usuario {
  id: number;
  name: string;
  email: string;
  role: RolUsuario;
  active: boolean;
}

export interface EntradaRegistro {
  name: string;
  email: string;
  password: string;
}

export interface SesionAutenticacion {
  authenticated: true;
  username: string;
  expires_at: string;
  role: RolUsuario;
  user: Usuario | null;
}

export interface EntradaAcceso {
  username: string;
  password: string;
}

export interface Equipo {
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

export type EntradaEquipo = Omit<Equipo, 'id'>;
export type CambiosEquipo = Partial<EntradaEquipo>;

export type EstadoReserva = 'confirmed' | 'cancelled';
export type OrigenReserva = 'portal' | 'admin' | 'csv' | 'legacy';

export interface Reserva {
  id: number;
  equipment_id: number;
  customer_name: string;
  customer_email: string;
  start_date: string;
  end_date: string;
  status: EstadoReserva;
  external_reference: string | null;
  customer_user_id?: number | null;
  origin?: OrigenReserva;
}

export type EntradaReserva = Omit<Reserva, 'id' | 'status' | 'external_reference' | 'customer_user_id' | 'origin'> & {
  external_reference?: string | null;
};

export interface FiltrosReservas {
  equipment_id?: number;
  status?: EstadoReserva;
  start_date?: string;
  end_date?: string;
  customer?: string;
  customer_user_id?: number;
  origin?: OrigenReserva;
}

export interface IntervaloFechas {
  start_date: string;
  end_date: string;
}

export interface EquipoPublico {
  id: number;
  name: string;
  category: string;
  public_description: string;
  technical_specs: Record<string, string>;
  image_url: string | null;
  image_fallback_url: string;
  active_reservations_count: number;
}

export interface FiltrosEquiposPublicos {
  q?: string;
  category?: string;
}

export type DisponibilidadPublica = { equipment_id: number } & (
  { status: 'select_dates'; start_date: null; end_date: null; available: null }
  | (IntervaloFechas & { status: 'available'; available: true })
  | (IntervaloFechas & { status: 'unavailable'; available: false })
);

export interface CalendarioDisponibilidadPublica extends IntervaloFechas {
  equipment_id: number;
  occupied_ranges: IntervaloFechas[];
  can_book: boolean;
  unavailable_end_dates?: string[];
}

export interface FechasReservaPublica {
  equipment_id: number;
  reservations: IntervaloFechas[];
}

export interface ReservaCliente extends IntervaloFechas {
  id: number;
  equipment_id: number;
  status: EstadoReserva;
}

export interface EntradaReservaCliente extends IntervaloFechas {
  equipment_id: number;
}

export interface ProductosGuardados {
  equipment_ids: number[];
}

export interface EntradaReservasConjuntasCliente extends IntervaloFechas {
  equipment_ids: number[];
}

export interface IncidenciaCliente {
  id: number;
  reservation_id: number;
  title: string;
  description: string;
  status: EstadoIncidencia;
  public_response: string;
}

export interface EntradaIncidenciaCliente {
  title: string;
  description: string;
}

export interface Disponibilidad extends IntervaloFechas {
  equipment_id: number;
  available: boolean;
  reason: 'equipment_inactive' | 'reservation_overlap' | 'blocking_incident' | null;
  conflicting_reservation_ids: number[];
}

export type PrioridadIncidencia = 'low' | 'medium' | 'high';
export type EstadoIncidencia = 'open' | 'in_progress' | 'resolved';

export interface Incidencia {
  id: number;
  equipment_id: number;
  title: string;
  description: string;
  priority: PrioridadIncidencia;
  blocking: boolean;
  status: EstadoIncidencia;
  resolution: string;
  confirmed_reservation_ids: number[];
  warning: string | null;
  reservation_id?: number | null;
  author_user_id?: number | null;
  public_response?: string;
  internal_notes?: string;
}

export interface EntradaIncidencia {
  equipment_id: number;
  title: string;
  description?: string;
  priority?: PrioridadIncidencia;
  blocking?: boolean;
}

export interface FiltrosIncidencias {
  equipment_id?: number;
  status?: EstadoIncidencia;
  priority?: PrioridadIncidencia;
  blocking?: boolean;
}

export interface CambioEstadoIncidencia {
  status: EstadoIncidencia;
  resolution?: string | null;
}

export interface ActualizacionIncidencia {
  priority?: PrioridadIncidencia;
  blocking?: boolean;
  public_response?: string;
  internal_notes?: string;
}

export type EstadoFilaImportacion = 'accepted' | 'already_imported' | 'rejected';

export type ResultadoFilaImportacion = {
  line: number;
  external_reference: string | null;
  message: string;
} & (
  { status: Exclude<EstadoFilaImportacion, 'rejected'>; reservation: Reserva }
  | { status: 'rejected'; reservation: null }
);

export interface TotalesImportacion {
  total: number;
  accepted: number;
  already_imported: number;
  rejected: number;
}

export interface InformeImportacion {
  totals: TotalesImportacion;
  rows: ResultadoFilaImportacion[];
}
