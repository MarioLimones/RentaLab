import { Link } from 'react-router-dom';
import { useAutenticacion } from '../autenticacion/contexto';
import { Aviso, CabeceraPagina } from '../componentes/interfaz';
import './cuenta.css';

export default function PaginaMiCuenta() {
  const { sesion } = useAutenticacion();
  const usuario = sesion?.user;
  return <div className="portal-account">
    <CabeceraPagina titulo="Mi cuenta" descripcion="Estos son los datos de tu cuenta de RentaLab." />
    {usuario ? <section className="portal-account-panel portal-account-profile" aria-labelledby="account-information-heading">
      <h2 id="account-information-heading">Información personal</h2>
      <dl className="portal-account-facts"><div><dt>Nombre</dt><dd>{usuario.name}</dd></div><div><dt>Correo electrónico</dt><dd>{usuario.email}</dd></div></dl>
      <p className="portal-account-muted">Tus reservas se vinculan a esta cuenta al confirmarlas.</p>
      <Link className="button button-secondary" to="/mis-reservas">Consultar mis reservas</Link>
    </section> : <Aviso tono="error">No se han podido consultar los datos de tu cuenta.</Aviso>}
  </div>;
}
