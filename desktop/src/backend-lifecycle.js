"use strict";

const {BackendSupervisor} = require("./backend-supervisor");

class BackendLifecycle {
  constructor(createSupervisor = (options) => new BackendSupervisor(options)) {
    this.createSupervisor = createSupervisor;
    this.current = null;
    this.launchPromise = null;
    this.closing = false;
  }

  preventLaunch() {this.closing = true;}
  resumeLaunch() {this.closing = false;}

  launch(options) {
    if (this.closing) return Promise.resolve(null);
    if (this.launchPromise) return this.launchPromise;
    this.launchPromise = this.#launch(options).finally(() => {this.launchPromise = null;});
    return this.launchPromise;
  }

  async #launch(options) {
    await this.current?.stop();
    if (this.closing) return null;
    const candidate = this.createSupervisor(options);
    this.current = candidate;
    const readiness = await candidate.start();
    if (this.closing) {
      await candidate.stop();
      return null;
    }
    return {supervisor:candidate, readiness};
  }

  async stop() {
    // Startup can be in-flight when quit arrives. Its own guarded completion
    // cleans up, then this final stop also covers a failed startup/retry.
    try {await this.launchPromise;} catch { /* Ownership remains retryable. */ }
    await this.current?.stop();
  }
}

module.exports = {BackendLifecycle};
