// Transformer.java — filter interfaces and implementations

package fixtures;

import java.util.*;

interface Transformer {
    Map<String, Object> transform(Map<String, Object> data);
}

interface ProcessorConfig {
    List<String> getRequiredFields();
    boolean isStrict();
}

class NormalizeFilter implements Transformer {
    @Override
    public Map<String, Object> transform(Map<String, Object> data) {
        Map<String, Object> result = new HashMap<>();
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            if (entry.getValue() instanceof String s) {
                result.put(entry.getKey(), s.trim().toLowerCase());
            } else {
                result.put(entry.getKey(), entry.getValue());
            }
        }
        return result;
    }
}

class RemoveNullFilter implements Transformer {
    @Override
    public Map<String, Object> transform(Map<String, Object> data) {
        Map<String, Object> result = new HashMap<>();
        for (Map.Entry<String, Object> entry : data.entrySet()) {
            if (entry.getValue() != null) {
                result.put(entry.getKey(), entry.getValue());
            }
        }
        return result;
    }
}
