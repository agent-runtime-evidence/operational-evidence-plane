package oep.builtins

test_now_ns_uses_cached_value if {
	now_ns({"nd_builtin_cache": {"time.now_ns": {"[]": 1777852800000000000}}}) == 1777852800000000000
}

test_http_send_uses_cached_value if {
	result := http_send(
		{"nd_builtin_cache": {"http.send": {`[{"method":"get","url":"https://example.test/status"}]`: {"status_code": 200}}}},
		{"method": "get", "url": "https://example.test/status"},
	)

	result.status_code == 200
}
