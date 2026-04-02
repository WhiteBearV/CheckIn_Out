const { Pool } = require("pg");
const cfg = require("./db_config.json");

const pool = new Pool(cfg[cfg.mode]);

module.exports = pool;
