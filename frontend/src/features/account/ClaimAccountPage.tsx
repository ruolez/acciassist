import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";

import { api, ApiError } from "../../api/client";
import type { User } from "../../api/types";
import { Logo } from "../../components/Logo";
import { claimErrorMessage } from "./stages";
import "./account.css";

const passwordSchema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Passwords don't match",
    path: ["confirm"],
  });
type PasswordForm = z.infer<typeof passwordSchema>;

const resendSchema = z.object({ email: z.string().email("Enter a valid email") });
type ResendForm = z.infer<typeof resendSchema>;

function ResendLinkForm() {
  const [sent, setSent] = useState(false);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ResendForm>({ resolver: zodResolver(resendSchema) });

  if (sent) {
    return (
      <div className="auth-note">
        If an account is waiting for that email, a fresh link is on its way. Check your
        inbox.
      </div>
    );
  }
  return (
    <form
      onSubmit={handleSubmit(async (values) => {
        await api("/auth/claim/resend", { method: "POST", body: values }).catch(() => {});
        setSent(true);
      })}
    >
      <div className="field">
        <label>Email</label>
        <input className="input" type="email" {...register("email")} />
        {errors.email && <span className="error-text">{errors.email.message}</span>}
      </div>
      <button className="btn btn-primary" type="submit" disabled={isSubmitting}>
        Send me a new link
      </button>
    </form>
  );
}

export function ClaimAccountPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);

  const verify = useQuery({
    queryKey: ["claim-verify", token],
    queryFn: () =>
      api<{ email: string; name: string }>("/auth/claim/verify", {
        method: "POST",
        body: { token },
      }),
    enabled: !!token,
    retry: false,
  });

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<PasswordForm>({ resolver: zodResolver(passwordSchema) });

  const onSubmit = async (values: PasswordForm) => {
    setFormError(null);
    try {
      await api<User>("/auth/claim", {
        method: "POST",
        body: { token, password: values.password },
      });
      await queryClient.invalidateQueries({ queryKey: ["user", "me"] });
      navigate("/account");
    } catch (e) {
      setFormError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
    }
  };

  let content;
  if (!token || verify.isError) {
    const code = verify.error instanceof ApiError ? verify.error.code : "invalid_token";
    content = (
      <>
        <h1>This link doesn&apos;t work</h1>
        <p className="auth-sub">{claimErrorMessage(code)}</p>
        {code === "token_used" ? (
          <div className="auth-links">
            <Link to="/login">Log in instead</Link>
            <Link to="/forgot-password">Forgot password?</Link>
          </div>
        ) : (
          <ResendLinkForm />
        )}
      </>
    );
  } else if (verify.isLoading || !verify.data) {
    content = <p className="auth-sub">Checking your link…</p>;
  } else {
    content = (
      <>
        <h1>Create your account</h1>
        <p className="auth-sub">
          Welcome, {verify.data.name}. Choose a password to follow your case progress.
        </p>
        {formError && <div className="error-text">{formError}</div>}
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="field">
            <label>Email</label>
            <input className="input" type="email" value={verify.data.email} disabled />
          </div>
          <div className="field">
            <label>Password</label>
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
            Create account →
          </button>
        </form>
      </>
    );
  }

  return (
    <div className="auth-page">
      <Logo size={44} withWordmark to="/" />
      <div className="card auth-card">{content}</div>
    </div>
  );
}
