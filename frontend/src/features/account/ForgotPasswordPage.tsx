import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { api } from "../../api/client";
import { Logo } from "../../components/Logo";
import "./account.css";

const schema = z.object({ email: z.string().email("Enter a valid email") });
type ForgotForm = z.infer<typeof schema>;

export function ForgotPasswordPage() {
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForgotForm>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: ForgotForm) => {
    await api("/auth/forgot-password", { method: "POST", body: values }).catch(() => {});
    setSent(true);
  };

  return (
    <div className="auth-page">
      <Logo size={44} withWordmark to="/" />
      <div className="card auth-card">
        <h1>Reset your password</h1>
        {sent ? (
          <div className="auth-note">
            If an account exists for that email, we&apos;ve sent a reset link. It expires in
            1 hour.
          </div>
        ) : (
          <>
            <p className="auth-sub">
              Enter the email you used and we&apos;ll send you a reset link.
            </p>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className="field">
                <label>Email</label>
                <input className="input" type="email" {...register("email")} autoFocus />
                {errors.email && <span className="error-text">{errors.email.message}</span>}
              </div>
              <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
                Send reset link
              </button>
            </form>
          </>
        )}
        <div className="auth-links">
          <Link to="/login">Back to log in</Link>
        </div>
      </div>
    </div>
  );
}
