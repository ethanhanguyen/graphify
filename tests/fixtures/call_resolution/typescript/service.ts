"""TypeScript call resolution fixture — defines functions and classes with method calls."""


function utilFunc(x: number): number {
    return x * 2;
}


class DataService {
    private data: number;

    constructor(init: number) {
        this.data = init;
    }

    fetch(): number {
        return this.data;
    }

    process(input: number): number {
        const doubled = utilFunc(input);
        const result = this.fetch();
        return result + doubled;
    }
}


class ApiService extends DataService {
    fetch(): number {
        const base = Math.floor(this.data);
        return base * 100;
    }
}
