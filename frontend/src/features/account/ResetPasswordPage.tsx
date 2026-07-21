import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { api, ApiError } from "../../api/client";
import { Logo } from "../../components/Logo";
import { usePageTitle } from "../../lib/usePageTitle";
import "./account.css";

const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });
type ResetForm = z.infer<typeof schema>;

export function ResetPasswordPage() {
  usePageTitle("Choose a new password", "AcciAssist");
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResetForm>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: ResetForm) => {
    setFormError(null);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        body: { token, password: values.password },
      });
      navigate("/login");
    } catch (e) {
      setFormError(
        e instanceof ApiError
          ? "This reset link is no longer valid. Request a new one below."
          : "Something went wrong. Try again.",
      );
    }
  };

  return (
    <div className="auth-page">
      <Logo size={44} withWordmark to="/" />
      <div className="card auth-card">
        <h1>Choose a new password</h1>
        {formError && (
          <>
            <div className="error-text">{formError}</div>
            <div className="auth-links">
              <Link to="/forgot-password">Request a new link</Link>
            </div>
          </>
        )}
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="field">
            <label>New password</label>
            <input className="input" type="password" {...register("password")} autoFocus />
            {errors.password && (
              <span className="error-text">{errors.password.message}</span>
            )}
          </div>
          <div className="field">
            <label>Confirm password</label>
            <input className="input" type="password" {...register("confirm")} />
            {errors.confirm && <span className="error-text">{errors.confirm.message}</span>}
          </div>
          <button className="btn btn-cta" type="submit" disabled={isSubmitting}>
            Set new password
          </button>
        </form>
        <div className="auth-links">
          <Link to="/login">Back to log in</Link>
        </div>
      </div>
    </div>
  );
}
