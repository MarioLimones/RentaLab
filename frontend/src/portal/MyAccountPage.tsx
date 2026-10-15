import { Link } from 'react-router-dom';
import { useAuth } from '../auth/context';
import { Notice, PageHeader } from '../components/ui';
import './account.css';

export default function MyAccountPage() {
  const { session } = useAuth();
  const user = session?.user;
  return <div className="portal-account">
    <PageHeader title="Mi cuenta" description="Estos son los datos de tu cuenta de RentaLab." />
    {user ? <section className="portal-account-panel portal-account-profile" aria-labelledby="account-information-heading">
      <h2 id="account-information-heading">Información personal</h2>
      <dl className="portal-account-facts"><div><dt>Nombre</dt><dd>{user.name}</dd></div><div><dt>Correo electrónico</dt><dd>{user.email}</dd></div></dl>
      <p className="portal-account-muted">Tus reservas se vinculan a esta cuenta al confirmarlas.</p>
      <Link className="button button-secondary" to="/mis-reservas">Consultar mis reservas</Link>
    </section> : <Notice tone="error">No se han podido consultar los datos de tu cuenta.</Notice>}
  </div>;
}
