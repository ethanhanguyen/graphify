// Processor.java — core data processing with inheritance and interface implementation

package fixtures;

import java.util.*;

public class DataProcessor {
    protected ProcessorConfig config;
    protected List<Transformer> transformers;

    public DataProcessor(ProcessorConfig config) {
        this.config = config;
        this.transformers = new ArrayList<>();
    }

    public void addTransformer(Transformer t) {
        this.transformers.add(t);
    }

    public Map<String, Object> process(Map<String, Object> data) {
        Map<String, Object> result = new HashMap<>(data);
        for (Transformer t : this.transformers) {
            result = t.transform(result);
        }
        return result;
    }

    public boolean validate(Map<String, Object> data) {
        for (String field : config.getRequiredFields()) {
            if (!data.containsKey(field)) {
                return false;
            }
        }
        return true;
    }
}

class JSONProcessor extends DataProcessor {
    public JSONProcessor(ProcessorConfig config) {
        super(config);
    }

    @Override
    public Map<String, Object> process(Map<String, Object> data) {
        return super.process(new HashMap<>(data));
    }
}
