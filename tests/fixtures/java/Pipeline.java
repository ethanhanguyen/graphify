// Pipeline.java — entry point composing processor and filters

package fixtures;

import java.util.*;

public class Pipeline {
    static class DefaultConfig implements ProcessorConfig {
        @Override
        public List<String> getRequiredFields() {
            return Arrays.asList("id", "name");
        }

        @Override
        public boolean isStrict() {
            return false;
        }
    }

    public static DataProcessor buildPipeline(String mode) {
        ProcessorConfig config = new DefaultConfig();
        DataProcessor proc = new DataProcessor(config);
        proc.addTransformer(new NormalizeFilter());
        proc.addTransformer(new RemoveNullFilter());
        return proc;
    }

    public static List<Map<String, Object>> runPipeline(
            List<Map<String, Object>> inputData) {
        DataProcessor proc = buildPipeline("default");
        List<Map<String, Object>> result = new ArrayList<>();
        for (Map<String, Object> d : inputData) {
            result.add(proc.process(d));
        }
        return result;
    }
}
