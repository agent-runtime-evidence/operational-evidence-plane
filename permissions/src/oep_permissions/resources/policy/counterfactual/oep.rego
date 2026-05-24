package oep.builtins

nd_builtin_cache(input_ctx) := cache if {
	cache := object.get(input_ctx, "nd_builtin_cache", {})
}

cached(input_ctx, builtin_name, cache_key) := value if {
	cache := nd_builtin_cache(input_ctx)
	builtin_cache := object.get(cache, builtin_name, {})
	value := builtin_cache[cache_key]
}

now_ns(input_ctx) := value if {
	value := cached(input_ctx, "time.now_ns", "[]")
} else := value if {
	value := time.now_ns()
}

http_send(input_ctx, request) := value if {
	# Cache keys use OPA's canonical JSON marshal format. Capture layers must
	# preserve that exact object shape so replay lookup stays byte-stable.
	cache_key := sprintf("[%s]", [json.marshal(request)])
	value := cached(input_ctx, "http.send", cache_key)
} else := value if {
	value := http.send(request)
}
