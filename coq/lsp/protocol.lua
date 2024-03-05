return (function()
  local sanitize = function(spec)
    local tb = {[vim.type_idx] = vim.types.dictionary}
    for k, v in pairs(spec) do
      if type(k) == "string" and type(v) == "number" then
        tb[k] = v
      end
    end
    return tb
  end

  local lookup = vim.empty_dict()

  for key, val in pairs(vim.lsp.protocol or {}) do
    if type(val) == "table" then
      lookup[key] = sanitize(val)
    end
  end

  return lookup
end)()
