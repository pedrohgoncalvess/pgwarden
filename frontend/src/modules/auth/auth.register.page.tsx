import { FormEvent, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useMutation } from "@tanstack/react-query";
import { login, register } from "@/modules/auth/auth.api";
import { authSelectors, useAuthStore } from "@/modules/auth/auth.store";

const MIN_NAME_LENGTH = 3;
const MIN_PASSWORD_LENGTH = 6;

function getRegisterErrorMessage(error: unknown): string {
  if (!(error instanceof Error)) {
    return "Registration failed. Review your details and try again.";
  }

  const message = error.message.toLowerCase();

  if (message.includes("email already registered")) {
    return "This email is already registered.";
  }

  if (message.includes("422")) {
    return "Invalid data. Check your name, email, and password.";
  }

  return "Registration failed. Review your details and try again.";
}

export function AuthRegisterPage() {
  const navigate = useNavigate();
  const setSessionFromAuthResponse = useAuthStore(authSelectors.setSessionFromAuthResponse);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const registerMutation = useMutation({
    mutationFn: register,
  });

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);

    const normalizedName = name.trim();
    if (normalizedName.length < MIN_NAME_LENGTH) {
      setFormError(`Name must be at least ${MIN_NAME_LENGTH} characters.`);
      return;
    }

    if (password.length < MIN_PASSWORD_LENGTH) {
      setFormError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }

    if (password !== confirmPassword) {
      setFormError("Passwords do not match.");
      return;
    }

    await registerMutation.mutateAsync({ name: normalizedName, email, password });
    const auth = await login({ email, password });
    setSessionFromAuthResponse(auth);
    await navigate({ to: "/" });
  };

  return (
    <section className="sf-panel mx-auto mt-16 w-full max-w-md p-6">
      <p className="sf-label font-mono text-accent-amber">Onboarding</p>
      <h1 className="mt-1 font-display text-2xl tracking-wide text-foreground">Create account</h1>

      <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
        <input
          className="app-input"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Full name"
          minLength={MIN_NAME_LENGTH}
          required
        />
        <input
          className="app-input"
          type="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Email"
          required
        />
        <input
          className="app-input"
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Password"
          minLength={MIN_PASSWORD_LENGTH}
          required
        />
        <input
          className="app-input"
          type="password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          placeholder="Confirm password"
          minLength={MIN_PASSWORD_LENGTH}
          required
        />

        {formError ? <p className="text-xs text-rose-400">{formError}</p> : null}
        {registerMutation.isError ? (
          <p className="text-xs text-rose-400">{getRegisterErrorMessage(registerMutation.error)}</p>
        ) : null}
        <button
          type="submit"
          className="app-button-primary w-full"
          disabled={registerMutation.isPending}
        >
          {registerMutation.isPending ? "Creating account..." : "Create account"}
        </button>
      </form>

      <div className="mt-4 rounded-md border border-border/70 bg-muted/30 p-3">
        <p className="sf-label text-foreground">Registration rules</p>
        <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-muted-foreground">
          <li>Name must have at least {MIN_NAME_LENGTH} characters.</li>
          <li>Email must be valid and not already registered.</li>
          <li>Password must have at least {MIN_PASSWORD_LENGTH} characters.</li>
          <li>Password and confirmation must match.</li>
        </ul>
      </div>

      <p className="mt-4 text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link className="app-link" to="/login">
          Login
        </Link>
      </p>
    </section>
  );
}
