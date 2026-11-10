package kr.mujuthaek.notification.delivery.email;

/** 메일 1통. {@code to}는 로그에 남기지 않아요. */
public record EmailMessage(String to, String subject, String text) {}
