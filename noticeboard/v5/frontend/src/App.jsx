import { useAuth } from "./auth/AuthContext";
import Header from "./components/Header";
import NoticeTicker from "./components/NoticeTicker";
import AuthPage from "./views/AuthPage";
import ManagerView from "./views/ManagerView";
import TraineeView from "./views/TraineeView";

export default function App() {
  const { currentUser } = useAuth();
  if (!currentUser) return <AuthPage />;

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
        {currentUser.role === "trainee" ? <TraineeView /> : <ManagerView />}
      </main>
      {/* key: a different trainee starts with a fresh "already seen" list */}
      {currentUser.role === "trainee" && <NoticeTicker key={currentUser.id} />}
    </div>
  );
}
