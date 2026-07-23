export class ArgusError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ArgusError";
  }
}

export class ArgusAuthError extends ArgusError {
  constructor(message: string) {
    super(message);
    this.name = "ArgusAuthError";
  }
}

export class ArgusAPIError extends ArgusError {
  status: number;
  constructor(status: number, message: string) {
    super(`HTTP ${status}: ${message}`);
    this.name = "ArgusAPIError";
    this.status = status;
  }
}
