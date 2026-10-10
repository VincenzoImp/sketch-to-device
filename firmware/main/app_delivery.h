#pragma once
#include "app_spec.h"

/* Starts persistence recovery and, when privately configured, HTTPS polling. */
bool app_delivery_start(const as_app *builtin);
